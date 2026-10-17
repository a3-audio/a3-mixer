// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "EncoderTurns.h"

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

int channelTurnsTo (int cursor, int target)
{
    constexpr int positions = 9;   // eight stems, then A
    return shortestInRing (cursor, target, positions);
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
