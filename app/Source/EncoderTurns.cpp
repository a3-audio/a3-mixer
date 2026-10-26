// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "EncoderTurns.h"
#include "DisplayPicture.h"

#include <array>
#include <cmath>

namespace desk::turns
{
int DragClicks::feed (float dragUpPixels)
{
    const int total = static_cast<int> (std::trunc (dragUpPixels / _per));
    const int clicks = total - _sent;
    _sent = total;
    return clicks;
}

namespace
{
int shortestInRing (int from, int to, int size)
{
    int d = ((to - from) % size + size) % size;
    if (d > size / 2)
        d -= size;
    return d;
}
}

int channelTurnsTo (int channel, int cursor, int slot)
{
    return shortestInRing (display::channelSlot (channel, cursor), slot, display::channelMeters);
}

int engineTurnsTo (int cursor, int slot)
{
    if (cursor >= display::channelMeters)   // Core's deck C or D: off the ring
        return 0;
    return shortestInRing (cursor, slot, display::channelMeters);
}

int returnTurnsTo (int cursor, int target)
{
    constexpr std::array<int, 3> along { 1, 0, 2 };   // STEM -> ANALOG -> CUE -> STEM
    const auto indexOf = [&] (int position) {
        for (int i = 0; i < 3; ++i)
            if (along[(size_t) i] == position)
                return i;
        return 0;
    };
    return shortestInRing (indexOf (cursor), indexOf (target), 3);
}
}
