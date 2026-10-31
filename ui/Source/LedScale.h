// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>

/** The desk's meter scales, a port of a3_mixer_meters.py. The shared fixture
    (software/tests/fixtures/desk-cases.json) holds the two to each other. */
namespace desk::leds
{
inline constexpr int channelLedCount = 8;
/** LED n lights when the peak reaches its threshold: a DJ mixer's meter
    (maintainer, 2026-10-07). */
inline constexpr std::array<double, channelLedCount> channelThresholdsDb { -36, -24, -18, -12, -9, -6, -3, 0 };

enum class LedColour { green, yellow, red };
LedColour channelLedColour (int index);

int channelLeds (double peakDb);
/** n of 8 LEDs lit is n/8 of a display bar: the bar steps as the LEDs do. */
double barFraction (double peakDb);

inline constexpr int mainLedCount = 32;
/** The output matrix's columns: SUB and the seven tops, one main_* meter each. */
inline constexpr int matrixColumns = 8;
inline constexpr double mainFloorDb = -60.0;
/** The output matrix's row, linear in dB from mainFloorDb to 0; the bottom row stays lit. */
int mainLedIndex (double db);

inline constexpr double meterFloorDb = -120.0;
double peakDb (float linearPeak);

/** The screen's meters: the same dB scale, many more segments (maintainer, 2026-10-30: "better
    lines and a lot more led-sections"). Every hardware LED, and every output row, is a whole
    group of segments, so the screen and the desk's LEDs never disagree at an LED's threshold;
    the hardware's scale above stays as it is. */
namespace screen
{
/** Green, yellow, orange, red: the hardware's two yellow LEDs (-9, -6) split in two. */
enum class Zone { green, yellow, orange, red };

/** A segment's least height: a light and a gap the eye still tells apart. */
inline constexpr float minSegmentPixels = 4.f;
inline constexpr int channelSegmentsMost = 8 * channelLedCount, mainSegmentsMost = 4 * mainLedCount;
/** Where the lowest LED's group starts: as far below -36 as the next LED lies above it. */
inline constexpr double channelFloorDb = -48.0;

/** How many segments a meter of this height draws: whole LED groups, none under minSegmentPixels. */
int channelSegments (float heightPixels);
int mainSegments (float heightPixels);

/** The peak at which channel segment `segment` of `segments` lights: its LED's threshold for
    the group's top segment, linear in dB from the LED below for the rest. */
double channelSegmentDb (int segment, int segments);
int channelSegmentsLit (double peakDb, int segments);
/** As mainLedIndex, finer: linear in dB from mainFloorDb to 0, the bottom segment always lit. */
int mainSegmentsLit (double db, int segments);

Zone zoneOf (double db);
Zone channelSegmentZone (int segment, int segments);
Zone mainSegmentZone (int segment, int segments);
}
}
