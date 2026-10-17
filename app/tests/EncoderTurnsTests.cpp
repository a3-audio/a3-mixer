// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "EncoderTurns.h"

using namespace desk::turns;

TEST (DragClicks, OneClickPerStepUpAndBack)
{
    DragClicks drag (20.f);
    EXPECT_EQ (drag.feed (19.f), 0);
    EXPECT_EQ (drag.feed (20.f), 1);
    EXPECT_EQ (drag.feed (65.f), 2);
    EXPECT_EQ (drag.feed (-1.f), -3);   // back past the start: no click is lost or invented
}

TEST (DragClicks, JitterAroundTheStartIsNoClick)
{
    DragClicks drag (20.f);
    EXPECT_EQ (drag.feed (3.f), 0);
    EXPECT_EQ (drag.feed (-3.f), 0);
}

// The truth: the channel's cursor moves "in a ring: left from the first stem
// is A, right from A the first stem". A slot tap sends the turns that get there.
TEST (SlotTurns, AChannelTakesTheShortWayRound)
{
    EXPECT_EQ (channelTurnsTo (0, 0), 0);
    EXPECT_EQ (channelTurnsTo (0, 4), 4);
    EXPECT_EQ (channelTurnsTo (0, 5), -4);
    EXPECT_EQ (channelTurnsTo (0, 8), -1);
    EXPECT_EQ (channelTurnsTo (8, 0), 1);
}

TEST (SlotTurns, TheReturnRingIsStemAnalogCue)
{
    EXPECT_EQ (returnTurnsTo (1, 0), 1);    // STEM -> ANALOG
    EXPECT_EQ (returnTurnsTo (0, 2), 1);    // ANALOG -> CUE
    EXPECT_EQ (returnTurnsTo (2, 1), 1);    // CUE -> STEM
    EXPECT_EQ (returnTurnsTo (1, 2), -1);
    EXPECT_EQ (returnTurnsTo (2, 2), 0);
}

// A knob that has no size yet (0 x 0) must not make a division by zero.
TEST (DragClicks, ANonPositiveStepIsOnePixel)
{
    EXPECT_EQ (DragClicks (0.f).feed (5.f), 5);
    EXPECT_EQ (DragClicks (-3.f).feed (-4.f), -4);
}
