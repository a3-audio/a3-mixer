// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include <array>
#include <limits>
#include <vector>

#include "LedScale.h"
#include "TestTruth.h"

using namespace desk::leds;

TEST (LedScale, ChannelLedsAreThePythons)
{
    const auto* cases = desk::test::fixture()["leds"]["channel"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_GT (cases->size(), 100);
    for (const auto& c : *cases)
    {
        const double db = c[0];
        EXPECT_EQ (channelLeds (db), static_cast<int> (c[1])) << db;
        EXPECT_DOUBLE_EQ (barFraction (db), static_cast<double> (c[2])) << db;
    }
}

TEST (LedScale, MainRowsAreThePythons)
{
    const auto* cases = desk::test::fixture()["leds"]["main"].getArray();
    ASSERT_NE (cases, nullptr);
    for (const auto& c : *cases)
        EXPECT_EQ (mainLedIndex (static_cast<double> (c[0])), static_cast<int> (c[1])) << static_cast<double> (c[0]);
}

TEST (LedScale, ColoursAreTheFirmwares)
{
    const auto* colours = desk::test::fixture()["leds"]["channel_colours"].getArray();
    ASSERT_NE (colours, nullptr);
    ASSERT_EQ (colours->size(), channelLedCount);
    for (int i = 0; i < channelLedCount; ++i)
    {
        const auto expected = colours->getReference (i).toString();
        const auto got = channelLedColour (i);
        EXPECT_EQ (juce::String (got == LedColour::green ? "green" : got == LedColour::yellow ? "yellow" : "red"), expected) << i;
    }
}

TEST (LedScale, SilenceAndNonsenseAreTheFloor)
{
    EXPECT_DOUBLE_EQ (peakDb (0.f), meterFloorDb);
    EXPECT_DOUBLE_EQ (peakDb (-1.f), meterFloorDb);
    EXPECT_DOUBLE_EQ (peakDb (std::numeric_limits<float>::quiet_NaN()), meterFloorDb);
    EXPECT_NEAR (peakDb (1.f), 0.0, 1e-9);
}

namespace
{
std::vector<double> fixtureDbs (const char* scale)
{
    std::vector<double> dbs;
    if (const auto* cases = desk::test::fixture()["leds"][scale].getArray())
        for (const auto& c : *cases)
            dbs.push_back (static_cast<double> (c[0]));
    return dbs;
}
}

// The screen's finer meters: lines, not dots -- many more of them than the hardware has LEDs.
TEST (ScreenMeterScale, TheRigsMetersCarryManySegments)
{
    EXPECT_EQ (screen::channelSegments (318.f), 64);
    EXPECT_EQ (screen::mainSegments (560.f), 128);
    EXPECT_GE (screen::channelSegments (318.f), 6 * channelLedCount);
}

TEST (ScreenMeterScale, ASmallMeterStillDrawsWholeLedGroups)
{
    for (float height : { 0.f, 10.f, 40.f, 100.f, 150.f, 250.f, 2000.f })
    {
        const int channel = screen::channelSegments (height), main = screen::mainSegments (height);
        EXPECT_EQ (channel % channelLedCount, 0) << height;
        EXPECT_EQ (main % mainLedCount, 0) << height;
        EXPECT_GE (channel, channelLedCount);
        EXPECT_GE (main, mainLedCount);
        if (height >= 100.f)
            EXPECT_GE (height / static_cast<float> (channel), screen::minSegmentPixels - 0.01f) << height;
    }
}

// Every hardware LED is a whole group of segments: the screen never says more or less than the desk's LEDs.
TEST (ScreenMeterScale, ChannelSegmentsAgreeWithTheHardwareLeds)
{
    const auto dbs = fixtureDbs ("channel");
    ASSERT_GT (dbs.size(), 100u);
    for (int segments : { 8, 32, 64 })
    {
        const int perLed = segments / channelLedCount;
        for (const auto db : dbs)
        {
            const int lit = screen::channelSegmentsLit (db, segments), leds = channelLeds (db);
            EXPECT_GE (lit, leds * perLed) << db << " at " << segments;
            EXPECT_LT (lit, leds == channelLedCount ? segments + 1 : (leds + 1) * perLed) << db << " at " << segments;
        }
    }
}

TEST (ScreenMeterScale, ChannelSegmentsRiseBetweenTheLeds)
{
    // Between -24 and -18 (LEDs 2 and 3) the hardware stands still; the screen moves.
    EXPECT_LT (screen::channelSegmentsLit (-23.0, 64), screen::channelSegmentsLit (-19.0, 64));
    EXPECT_EQ (screen::channelSegmentsLit (screen::channelFloorDb - 1.0, 64), 0);
    EXPECT_EQ (screen::channelSegmentsLit (0.0, 64), 64);
}

TEST (ScreenMeterScale, MainSegmentsAgreeWithTheHardwareRows)
{
    const auto dbs = fixtureDbs ("main");
    ASSERT_FALSE (dbs.empty());
    for (const auto db : dbs)
        EXPECT_EQ ((screen::mainSegmentsLit (db, 128) - 1) / 4, mainLedIndex (db)) << db;
    EXPECT_EQ (screen::mainSegmentsLit (-120.0, 128), 1);   // the bottom stays lit, as on the hardware
}

// Green, yellow, orange, red: the hardware's yellow LEDs split in two, on the same dB.
TEST (ScreenMeterScale, ZonesFollowTheLedColours)
{
    using screen::Zone;
    constexpr int perLed = 8, segments = 8 * perLed;
    const std::array<Zone, channelLedCount> zones { Zone::green, Zone::green, Zone::green, Zone::green,
                                                    Zone::yellow, Zone::orange, Zone::red, Zone::red };
    for (int s = 0; s < segments; ++s)
        EXPECT_EQ (screen::channelSegmentZone (s, segments), zones[(size_t) (s / perLed)]) << s;
    EXPECT_EQ (screen::mainSegmentZone (0, 128), Zone::green);
    EXPECT_EQ (screen::mainSegmentZone (127, 128), Zone::red);
    EXPECT_EQ (screen::zoneOf (-12.0), Zone::green);
    EXPECT_EQ (screen::zoneOf (-10.0), Zone::yellow);
    EXPECT_EQ (screen::zoneOf (-7.0), Zone::orange);
    EXPECT_EQ (screen::zoneOf (-3.0), Zone::red);
}
