// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "LedScale.h"

#include <algorithm>
#include <cmath>

namespace desk::leds
{
LedColour channelLedColour (int index)
{
    if (index < 4)
        return LedColour::green;
    return index < 6 ? LedColour::yellow : LedColour::red;
}

int channelLeds (double peakDb)
{
    int lit = 0;
    for (const auto threshold : channelThresholdsDb)
        if (peakDb >= threshold)
            ++lit;
    return lit;
}

double barFraction (double peakDb)
{
    return channelLeds (peakDb) / static_cast<double> (channelLedCount);
}

int mainLedIndex (double db)
{
    const auto share = (std::clamp (db, mainFloorDb, 0.0) - mainFloorDb) / -mainFloorDb;
    return std::min (static_cast<int> (share * mainLedCount), mainLedCount - 1);
}

double peakDb (float linearPeak)
{
    if (! std::isfinite (linearPeak) || linearPeak <= 0.f)
        return meterFloorDb;
    return std::max (meterFloorDb, 20.0 * std::log10 (static_cast<double> (linearPeak)));
}
}
