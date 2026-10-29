#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The delay list on the AUX-RTN encoder (spec delay-params).

Hardware-free like a3_mixer_encoders. Design history:

2026-10-29, first design: one parameter at a time -- a page. The turn changed
the page's value, a short push stepped the page, a hold of half a second
cued, four quiet seconds went back to BEAT.

2026-10-29, after the maintainer had it on the rig (round 2, rulings
R22-R25): *"alle 4 delay parameter untereinander ... mit enc push wechselt
man zwischen parameter/value. CUE ist ein parameter."* The pages, the hold
and the fall back to BEAT are gone. The return shows five rows -- BEAT,
FEEDBK, COLOR, SPREAD, CUE -- and the encoder has two modes, toggled by a
press (the press edge PushHoldOff accepts; there is no hold timing):

- select, the start mode, the cursor on BEAT: a turn moves the cursor, which
  stops at BEAT and at CUE (R24, no wrap);
- edit: a turn changes the row under the cursor. A delay row's turn goes to
  Core as clicks (Core steps it and announces it, so the desk keeps what
  Core says). The CUE row is a switch: a right turn is on, a left turn off
  (R23). Core's word is a toggle (aux-return.stem.push), so the desk sends it
  only when the lamp it shows (aux-return.cue.led) says the cue is the other
  way -- a fast turn over several detents cannot flicker the cue. The lamp
  answers a round trip later, so a push waits for it (CUE_SETTLE_SECONDS)
  before the same direction may push again.

Edit falls back to select after FALLBACK_SECONDS without a turn or press, the
cursor staying on its row (R22): a hand that walked away must not leave the
encoder changing a delay the next time it is touched. The mode and the cursor
are the desk's own UI state, the values are Core's.
"""

import math
import threading
import time

from a3_mixer_encoders import encoder_message

#: The rows in the order they stand on the display.
ROWS = ("beat", "feedback", "color", "spread", "cue")

#: The rows Core owns a value of; CUE is a switch on the return.
DELAY_ROWS = ROWS[:4]

#: Core's value words, one per delay row.
VALUE_KEYS = tuple("aux-return.delay." + row for row in DELAY_ROWS)

SELECT = "select"
EDIT = "edit"

#: Quiet time in edit after which the encoder is selecting again (R22; one
#: constant if the maintainer wants it otherwise).
FALLBACK_SECONDS = 4.0

#: How long a cue push waits for the lamp to answer before the same direction
#: may push again. Not measured on the desk: a round trip to Core is a few
#: milliseconds, a second is clear of it and short enough to try again.
CUE_SETTLE_SECONDS = 1.0

RETURN_ENCODER = 4


def _timer(seconds, then):
    timer = threading.Timer(seconds, then)
    timer.daemon = True
    timer.start()


class DelayList:
    """The mode and the cursor of the return encoder.

    `send(*message)` goes to Core, `show(mode, cursor)` is told when either
    changes, `cue_is_on()` is the cue lamp as the desk shows it.
    `later(seconds, then)` runs `then` once after `seconds`; a timer is never
    cancelled -- each carries the number of the activity it belongs to and
    does nothing once there was a newer one."""

    def __init__(self, osc, send, show, cue_is_on, clock=time.monotonic, later=_timer):
        self._osc = osc
        self._send = send
        self._show = show
        self._cue_is_on = cue_is_on
        self._clock = clock
        self._later = later
        self._lock = threading.Lock()
        self.mode = SELECT
        self.cursor = 0
        self._activity = 0
        self._cue_asked = None   # (wanted state, when) of the last cue push

    def turn(self, clicks):
        if clicks == 0:
            return
        with self._lock:
            if self.mode == SELECT:
                self._move(clicks)
                return
            self._touch()
            row = ROWS[self.cursor]
        if row == "cue":
            self._turn_cue(clicks > 0)
            return
        message = encoder_message(self._osc, RETURN_ENCODER, clicks, page=row)
        if message is not None:
            self._send(*message)

    def press(self):
        """An accepted press (PushHoldOff): select <-> edit."""
        with self._lock:
            if self.mode == SELECT:
                self.mode = EDIT
                self._touch()
            else:
                self.mode = SELECT
            self._show(self.mode, self.cursor)

    def _move(self, clicks):
        """Select: the cursor, clamped. Under the lock."""
        cursor = min(len(ROWS) - 1, max(0, self.cursor + clicks))
        if cursor == self.cursor:
            return
        self.cursor = cursor
        self._show(self.mode, self.cursor)

    def _turn_cue(self, want_on):
        """Edit on CUE: push Core's toggle only if the cue is the other way
        and no push for this direction is still waiting for its lamp."""
        if bool(self._cue_is_on()) == want_on:
            return
        now = self._clock()
        with self._lock:
            asked = self._cue_asked
            if asked is not None and asked[0] == want_on \
                    and now - asked[1] < CUE_SETTLE_SECONDS:
                return
            self._cue_asked = (want_on, now)
        self._send(self._osc.address("aux-return.stem.push"), 1)

    def _touch(self):
        """Activity in edit: the four seconds start over. Under the lock."""
        self._activity += 1
        activity = self._activity
        self._later(FALLBACK_SECONDS, lambda: self._quiet(activity))

    def _quiet(self, activity):
        with self._lock:
            if self._activity != activity or self.mode != EDIT:
                return
            self.mode = SELECT
            self._show(self.mode, self.cursor)


class DelayState:
    """The last value of each delay row, None until Core speaks, and the mode
    and cursor on show. Hands all three to `show(mode, cursor, values)` on
    every change. Receiving a value sends nothing back."""

    def __init__(self, show):
        self._show = show
        self._lock = threading.Lock()
        self._mode = SELECT
        self._cursor = 0
        self._values = {row: None for row in DELAY_ROWS}

    def show_view(self, mode, cursor):
        with self._lock:
            self._mode, self._cursor = mode, cursor
            self._push()

    def set_value(self, row, value):
        with self._lock:
            self._values[row] = value
            self._push()

    def _push(self):
        self._show(self._mode, self._cursor, dict(self._values))


def value_announcement(args):
    """The float of a value word, None if the message is damaged."""
    if len(args) != 1 or isinstance(args[0], bool):
        return None
    try:
        value = float(args[0])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None
