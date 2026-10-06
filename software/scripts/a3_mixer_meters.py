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
