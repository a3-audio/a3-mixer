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


def channel_leds(peak_db):
    """How many of a channel's LEDs a peak of `peak_db` dBFS lights."""
    return sum(1 for threshold in CHANNEL_LED_THRESHOLDS_DB if peak_db >= threshold)


def channel_vu_line(slot, peak_db):
    """The firmware's VU line for a channel: both fields carry the top lit
    LED's index (count - 1, -1 = dark). The firmware draws 0..index in fixed
    colours; an older firmware draws the same bar, green with its top red."""
    top_index = channel_leds(peak_db) - 1
    return f"VU:{slot}:{top_index}:{top_index}"
