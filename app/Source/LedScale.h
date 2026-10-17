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
}
