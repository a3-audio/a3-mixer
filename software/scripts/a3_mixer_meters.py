# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A channel's input LEDs show the louder side of its stereo meter (spec
stereo-channel-meters). Levels are linear, as the analyzer sends them.

Every meter on the desk -- channel LEDs, main LEDs, the displays' bars --
moves the same way (meter-ballistics, 2026-10-07): the sources send raw
peaks, and MeterBallistics turns them into a bar and a held peak."""

import math
from collections import namedtuple


def louder(left, right):
    """(peak, rms) of the louder side: each the max of the two, as a DJ
    mixer's meter shows a stereo channel."""
    return max(left[0], right[0]), max(left[1], right[1])


class StereoInputs:
    """The last (peak, rms) of each side of the four inputs. L and R arrive
    as separate messages, so a side's level is held until its next one; a
    side not heard yet is silence."""

    def __init__(self, channels=4):
        self._levels = [[(0.0, 0.0), (0.0, 0.0)] for _ in range(channels)]

    def note(self, channel, side, peak, rms):
        """Hold `side`'s level and return the channel's louder side."""
        sides = self._levels[channel]
        sides[side] = (peak, rms)
        return louder(*sides)


# The channel LEDs' scale, bottom to top, in dBFS peak: LED n lights when the
# peak reaches its threshold. A DJ mixer's meter, not a linear one -- the top
# two are red and mean near clip, the top one clip (0 dBFS). Decided by the
# maintainer 2026-10-07; the colours are the firmware's (channelLedColour).
CHANNEL_LED_THRESHOLDS_DB = (-36, -24, -18, -12, -9, -6, -3, 0)


#: Each LED's colour, as the firmware's channelLedColour has them.
CHANNEL_LED_COLOURS = ("green",) * 4 + ("yellow",) * 2 + ("red",) * 2
#: Where the LEDs turn yellow and red, as shares of a display bar: the
#: bottom of the first yellow and of the first red LED's segment. The
#: displays are monochrome; they mark these two heights beside every bar.
YELLOW_FROM_FRACTION = CHANNEL_LED_COLOURS.index("yellow") / len(CHANNEL_LED_COLOURS)
RED_FROM_FRACTION = CHANNEL_LED_COLOURS.index("red") / len(CHANNEL_LED_COLOURS)


def channel_leds(peak_db):
    """How many of a channel's LEDs a peak of `peak_db` dBFS lights."""
    return sum(1 for threshold in CHANNEL_LED_THRESHOLDS_DB if peak_db >= threshold)


def bar_fraction(peak_db):
    """How much of a display bar (0.0-1.0) a peak of `peak_db` dBFS fills:
    exactly the LEDs it lights, n of 8 is n/8 -- the bar steps as the LEDs
    do, nothing between two steps and nothing below the first LED
    (2026-10-07; it used to run linear in dB between the thresholds, with a
    sliver below -36 dBFS, and stood over the yellow mark while only green
    LEDs were lit)."""
    return channel_leds(peak_db) / len(CHANNEL_LED_THRESHOLDS_DB)


def channel_vu_line(slot, level_db, hold_db):
    """The firmware's VU line for a channel: the bar's top LED, then the
    held peak's LED (index = count - 1, -1 = dark). The firmware draws
    0..bar in fixed colours and lights the hold LED in its own; an older
    firmware reads only the bar."""
    bar_index = channel_leds(level_db) - 1
    hold_index = channel_leds(hold_db) - 1
    return f"VU:{slot}:{bar_index}:{hold_index}"


#: The main meter's scale: 32 rows, linear in dB from MAIN_FLOOR_DB to 0.
MAIN_LED_COUNT = 32
MAIN_FLOOR_DB = -60.0


def main_led_index(db):
    """The main meter's row for `db` dBFS: 0 at and below MAIN_FLOOR_DB (the
    bottom row stays lit, as it always has), 31 at full scale and above."""
    share = (min(max(db, MAIN_FLOOR_DB), 0.0) - MAIN_FLOOR_DB) / -MAIN_FLOOR_DB
    return min(int(share * MAIN_LED_COUNT), MAIN_LED_COUNT - 1)


def main_vu_line(slot, level_db, hold_db):
    """The firmware's VU line for a main meter, in the field order the
    firmware has always read there -- the single dot first, the bar second
    --, so an older firmware draws it right: the dot is the held peak, the
    bar the ballistic level."""
    return f"VU:{slot}:{main_led_index(hold_db)}:{main_led_index(level_db)}"


# -- ballistics ----------------------------------------------------------

#: How a meter moves, Core's numbers (the truth's "meters" block): the
#: attack in ms (0 = a new peak shows at once), the release in dB a second,
#: and how long the highest recent peak is held before it falls at the
#: release rate.
MeterTiming = namedtuple("MeterTiming", "attack_ms release_db_per_second peak_hold_seconds",
                         defaults=(0.0, 20.0, 1.5))
#: Decided 2026-10-07; the desk uses them when the truth has no block.
DEFAULT_METER_TIMING = MeterTiming()

#: Where every meter bottoms out: far below any LED and any display bar,
#: and finite, so the arithmetic never meets -inf.
METER_FLOOR_DB = -120.0


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def peak_db(peak):
    """A linear peak in dBFS, METER_FLOOR_DB for silence and anything odd."""
    if not _number(peak) or peak <= 0:
        return METER_FLOOR_DB
    return max(METER_FLOOR_DB, 20 * math.log10(peak))


#: What a meter shows: its bar and its held peak, in dBFS.
Reading = namedtuple("Reading", "level_db hold_db")


class MeterBallistics:
    """One meter's bar and held peak from raw peaks (dBFS), on `clock`.

    Only differences of the clock count: the desk's monotonic clock starts
    at the Pi's boot, and the first feed shows its peak whatever it says.
    A clock that steps back is no time passed.
    """

    def __init__(self, timing=DEFAULT_METER_TIMING, clock=None):
        if clock is None:
            import time
            clock = time.monotonic
        self._timing = timing
        self._clock = clock
        self._last = None
        self._level = METER_FLOOR_DB
        self._held = METER_FLOOR_DB
        self._held_at = None

    def feed(self, peak):
        """The Reading after the raw peak `peak` (dBFS) arrived now."""
        now = self._clock()
        dt = 0.0 if self._last is None else max(0.0, now - self._last)
        self._last = now
        peak = max(METER_FLOOR_DB, peak)
        self._level = self._rise(max(METER_FLOOR_DB, self._fallen(self._level, dt)), peak, dt)
        hold = self._hold_now(now)
        if peak >= hold:
            self._held, self._held_at, hold = peak, now, peak
        return Reading(self._level, max(hold, self._level))

    def _fallen(self, level, seconds):
        return level - self._timing.release_db_per_second * seconds

    def _rise(self, fallen, peak, dt):
        """Where the bar stands after falling to `fallen` and meeting
        `peak`: the peak at once without an attack time, else that far of
        the way up as dt is of the attack."""
        if peak <= fallen:
            return fallen
        attack = self._timing.attack_ms / 1000.0
        if attack <= 0:
            return peak
        return fallen + (peak - fallen) * min(1.0, dt / attack)

    def _hold_now(self, now):
        """The held peak now: held for peak_hold_seconds, then falling."""
        if self._held_at is None:
            return METER_FLOOR_DB
        falling = max(0.0, now - self._held_at - self._timing.peak_hold_seconds)
        return max(METER_FLOOR_DB, self._fallen(self._held, falling))
