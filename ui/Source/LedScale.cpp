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

namespace screen
{
namespace
{
int wholeGroups (float heightPixels, int group, int most)
{
    const int fitting = static_cast<int> (std::max (0.f, heightPixels) / minSegmentPixels) / group * group;
    return std::clamp (fitting, group, most);
}
}

int channelSegments (float heightPixels) { return wholeGroups (heightPixels, channelLedCount, channelSegmentsMost); }

int mainSegments (float heightPixels) { return wholeGroups (heightPixels, mainLedCount, mainSegmentsMost); }

double channelSegmentDb (int segment, int segments)
{
    const int perLed = std::max (1, segments / channelLedCount);
    const int led = std::clamp (segment / perLed, 0, channelLedCount - 1);
    const double below = led == 0 ? channelFloorDb : channelThresholdsDb[(size_t) led - 1];
    const double share = static_cast<double> (segment % perLed + 1) / perLed;
    return below + share * (channelThresholdsDb[(size_t) led] - below);
}

int channelSegmentsLit (double peakDb, int segments)
{
    int lit = 0;
    while (lit < segments && peakDb >= channelSegmentDb (lit, segments))
        ++lit;
    return lit;
}

int mainSegmentsLit (double db, int segments)
{
    const auto share = (std::clamp (db, mainFloorDb, 0.0) - mainFloorDb) / -mainFloorDb;
    return std::min (static_cast<int> (share * segments), segments - 1) + 1;
}

Zone zoneOf (double db)
{
    // The firmware's colours by LED: green to the -12 LED, then -9, -6, and red above.
    if (db <= channelThresholdsDb[3])
        return Zone::green;
    if (db <= channelThresholdsDb[4])
        return Zone::yellow;
    return db <= channelThresholdsDb[5] ? Zone::orange : Zone::red;
}

Zone channelSegmentZone (int segment, int segments) { return zoneOf (channelSegmentDb (segment, segments)); }

Zone mainSegmentZone (int segment, int segments)
{
    // The segment's top: a segment reaching past -6 dB is red, as the LED at -3 would be.
    return zoneOf (mainFloorDb + -mainFloorDb * static_cast<double> (segment + 1) / segments);
}
}
}
