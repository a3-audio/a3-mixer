// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include <limits>

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
