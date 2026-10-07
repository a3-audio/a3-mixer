# SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A channel's input LEDs show the louder side of its stereo meter (spec
stereo-channel-meters). Levels are linear, as the analyzer sends them."""


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
#: Where the LEDs turn yellow and red. The displays are monochrome; they
#: mark these two levels beside every bar instead.
YELLOW_FROM_DB = CHANNEL_LED_THRESHOLDS_DB[CHANNEL_LED_COLOURS.index("yellow")]
RED_FROM_DB = CHANNEL_LED_THRESHOLDS_DB[CHANNEL_LED_COLOURS.index("red")]

#: Where a display bar is empty. Below the first LED the bar runs on to here
#: at the slope of the first LED step (12 dB an eighth, -36 -> -24): no kink
#: at the first LED, and a quiet input still shows as a sliver -- A is there
#: so the DJ sees something on analog before switching to it.
BAR_FLOOR_DB = 2 * CHANNEL_LED_THRESHOLDS_DB[0] - CHANNEL_LED_THRESHOLDS_DB[1]

# (dBFS, share of the bar) corners of the scale: the floor empty, then each
# LED's threshold at its own eighth.
_BAR_CORNERS = ((BAR_FLOOR_DB, 0.0),) + tuple(
    (threshold, count / len(CHANNEL_LED_THRESHOLDS_DB))
    for count, threshold in enumerate(CHANNEL_LED_THRESHOLDS_DB, start=1))


def _between(corners, value):
    """Piecewise-linear through `corners` ((x, y), rising in x), clamped
    to the first and last y."""
    if value <= corners[0][0]:
        return corners[0][1]
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        if value <= x1:
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    return corners[-1][1]


def bar_fraction(peak_db):
    """How much of a display bar (0.0-1.0) a peak of `peak_db` dBFS fills:
    the same scale as the LEDs -- a peak that lights n of them fills at
    least n/8 of the bar and less than (n+1)/8. Linear in dB between two
    thresholds."""
    return _between(_BAR_CORNERS, peak_db)


def bar_db(fraction):
    """The dBFS a bar filled to `fraction` stands for: bar_fraction's
    inverse, BAR_FLOOR_DB for an empty bar."""
    return _between(tuple((y, x) for x, y in _BAR_CORNERS), fraction)


def channel_leds(peak_db):
    """How many of a channel's LEDs a peak of `peak_db` dBFS lights."""
    return sum(1 for threshold in CHANNEL_LED_THRESHOLDS_DB if peak_db >= threshold)


def channel_vu_line(slot, peak_db):
    """The firmware's VU line for a channel: both fields carry the top lit
    LED's index (count - 1, -1 = dark). The firmware draws 0..index in fixed
    colours; an older firmware draws the same bar, green with its top red."""
    top_index = channel_leds(peak_db) - 1
    return f"VU:{slot}:{top_index}:{top_index}"
