#!/usr/bin/python

# SPDX-FileCopyrightText: 2026 Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The delay page on the AUX-RTN encoder (spec delay-params).

Hardware-free like a3_mixer_encoders. The return encoder turns the value of
the page it stands on (Core steps it and announces it, so the desk sends
clicks and keeps what Core says); a short push steps the page, a hold of
HOLD_SECONDS cues the return as the push alone used to; four quiet seconds
go back to BEAT. The page is the desk's own UI state, the values are Core's.
"""

import math
import threading
import time

from a3_mixer_encoders import PUSH_HOLD_OFF_SECONDS, encoder_message

#: The pages in the order a short push steps through them.
PAGES = ("beat", "feedback", "color", "spread")

#: Core's value words, one per page.
VALUE_KEYS = tuple("aux-return.delay." + page for page in PAGES)

#: A push held this long is the cue, at that moment. Decided with the
#: maintainer's brief (ruling R6); not measured on the desk.
HOLD_SECONDS = 0.5

#: Quiet time on the return encoder after which the page is BEAT again.
FALLBACK_SECONDS = 4.0

RETURN_ENCODER = 4


def _timer(seconds, then):
    timer = threading.Timer(seconds, then)
    timer.daemon = True
    timer.start()


class DelayPager:
    """The page, the hold and the fallback of the return encoder.

    `send(*message)` goes to Core, `show_page(page)` is told when the page
    changes. `later(seconds, then)` runs `then` once after `seconds`; a timer
    is never cancelled -- each carries the number of the activity it belongs
    to and does nothing once there was a newer one."""

    def __init__(self, osc, send, show_page, clock=time.monotonic, later=_timer):
        self._osc = osc
        self._send = send
        self._show_page = show_page
        self._clock = clock
        self._later = later
        self._lock = threading.Lock()
        self.page = PAGES[0]
        self._activity = 0
        self._press = 0
        self._pressed_at = None
        self._cued = False

    def turn(self, clicks):
        message = encoder_message(self._osc, RETURN_ENCODER, clicks, page=self.page)
        if message is None:
            return
        self._send(*message)
        with self._lock:
            self._touch()

    def press(self):
        """An accepted press (PushHoldOff)."""
        with self._lock:
            self._pressed_at = self._clock()
            self._cued = False
            self._press += 1
            press = self._press
            self._touch()
        self._later(HOLD_SECONDS, lambda: self._held(press))

    def release(self):
        """A release edge of the switch."""
        with self._lock:
            pressed_at = self._pressed_at
            # A release this soon after the press is the contact bouncing, no
            # hand lets go in fifty milliseconds.
            if pressed_at is None or self._clock() - pressed_at < PUSH_HOLD_OFF_SECONDS:
                return
            self._pressed_at = None
            self._touch()
            if self._cued:
                return
            page = PAGES[(PAGES.index(self.page) + 1) % len(PAGES)]
            self._set_page(page)

    def _touch(self):
        """Activity on the encoder: the four seconds start over. Under the lock."""
        self._activity += 1
        activity = self._activity
        self._later(FALLBACK_SECONDS, lambda: self._quiet(activity))
        return activity

    def _held(self, press):
        with self._lock:
            if self._press != press or self._pressed_at is None or self._cued:
                return
            self._cued = True
            self._touch()
        self._send(self._osc.address("aux-return.stem.push"), 1)

    def _quiet(self, activity):
        with self._lock:
            if self._activity != activity or self.page == PAGES[0]:
                return
            self._set_page(PAGES[0])

    def _set_page(self, page):
        self.page = page
        self._show_page(page)


class DelayState:
    """The last value of each page, None until Core speaks, and the page on
    show. Hands both to `show(page, values)` on every change. Receiving a
    value sends nothing back."""

    def __init__(self, show):
        self._show = show
        self._lock = threading.Lock()
        self._page = PAGES[0]
        self._values = {page: None for page in PAGES}

    def show_page(self, page):
        with self._lock:
            self._page = page
            self._push()

    def set_value(self, page, value):
        with self._lock:
            self._values[page] = value
            self._push()

    def _push(self):
        self._show(self._page, dict(self._values))


def value_announcement(args):
    """The float of a value word, None if the message is damaged."""
    if len(args) != 1 or isinstance(args[0], bool):
        return None
    try:
        value = float(args[0])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None
