# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A stem's level for the desk's displays (issue a3-system#71).

The beat-analyzer sends 8 stem meters 25 times a second. A display redraw
costs ~30 ms on the Pi 3B+, so the levels are coarsened to STEPS steps and a
gate hands them to the displays at most every `interval` seconds, and only
when a step changed. Pure: the clock is passed in.
"""

import math
import time

STEPS = 6
FLOOR_DB = -48.0    # below this: no bar
PAIRS = 8


def level_step(peak):
    """0 (no bar) .. STEPS for a linear peak; anything odd is 0 or STEPS."""
    if not peak > 0:            # 0, negative, NaN
        return 0
    db = 20 * math.log10(min(peak, 1.0))
    if db < FLOOR_DB:
        return 0
    return min(STEPS, 1 + int((db - FLOOR_DB) / (-FLOOR_DB / STEPS)))


class LevelGate:
    """Collects steps as they arrive; due() hands all 8 out when one changed
    and `interval` has passed since the last hand-out."""

    def __init__(self, interval=0.1, clock=time.monotonic):
        self.interval = interval
        self._clock = clock
        self.steps = {pair: 0 for pair in range(1, PAIRS + 1)}
        self.pending = False
        self._last = None

    def update(self, pair, step):
        if self.steps.get(pair) != step:
            self.steps[pair] = step
            self.pending = True

    def due(self):
        if not self.pending:
            return None
        now = self._clock()
        if self._last is not None and now - self._last < self.interval:
            return None
        self._last = now
        self.pending = False
        return dict(self.steps)
