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

// The truth: on channel n the cursor takes only n-1, 4+n-1 and 8 (D1, D2, A),
// "in a ring". A slot tap (meter 0-2) sends the turns that get there; a cursor
// off the ring counts as A.
TEST (SlotTurns, AChannelRingIsD1D2A)
{
    EXPECT_EQ (channelTurnsTo (1, 1, 1), 1);
    EXPECT_EQ (channelTurnsTo (1, 5, 2), 1);
    EXPECT_EQ (channelTurnsTo (1, 8, 0), 1);
    EXPECT_EQ (channelTurnsTo (1, 1, 2), -1);
    EXPECT_EQ (channelTurnsTo (1, 1, 0), 0);
    EXPECT_EQ (channelTurnsTo (1, 0, 0), 1);
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

// Engine mode: the ring is AN | A | B by Core's numbers, the same shortest way round.
TEST (DeskRing, TheEngineRingTurnsTheShortestWay)
{
    EXPECT_EQ (engineTurnsTo (0, 1), 1);
    EXPECT_EQ (engineTurnsTo (2, 0), 1);    // B -> AN wraps
    EXPECT_EQ (engineTurnsTo (0, 2), -1);
    EXPECT_EQ (engineTurnsTo (1, 1), 0);
}
