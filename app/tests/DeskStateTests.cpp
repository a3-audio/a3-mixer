// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskState.h"

using desk::DeskState;

TEST (DeskState, NothingIsKnownUntilCoreTells)
{
    DeskState s (3);
    EXPECT_FALSE (s.known (0));
    s.setFromPeer (0, 0.4f);
    EXPECT_TRUE (s.known (0));
    EXPECT_FLOAT_EQ (s.value (0), 0.4f);
    EXPECT_FALSE (s.marked (0));
}

TEST (DeskState, ATouchStoresAndRaisesTheRing)
{
    DeskState s (3);
    s.setFromPeer (1, 0.2f);
    s.setFromTouch (1, 0.7f);
    EXPECT_FLOAT_EQ (s.value (1), 0.7f);
    EXPECT_TRUE (s.marked (1));
}

TEST (DeskState, ADifferentRelayClearsTheRing)
{
    DeskState s (3);
    s.setFromTouch (1, 0.7f);
    s.setFromPeer (1, 0.3f);   // the hardware knob was touched: its position wins
    EXPECT_FLOAT_EQ (s.value (1), 0.3f);
    EXPECT_FALSE (s.marked (1));
}

// Review focus 4: a recall someone else started repeats this desk's own value
// to everyone; the hardware still stands elsewhere, so the ring stays.
TEST (DeskState, TheSameValueComingBackKeepsTheRing)
{
    DeskState s (3);
    s.setFromTouch (2, 0.55f);
    s.setFromPeer (2, 0.55f);
    EXPECT_TRUE (s.marked (2));
}

TEST (DeskState, AGrabHoldsRelaysUntilRelease)
{
    DeskState s (3);
    s.grab (0);
    s.setFromTouch (0, 0.6f);
    s.setFromPeer (0, 0.1f);   // another surface moved it meanwhile
    EXPECT_FLOAT_EQ (s.value (0), 0.6f);
    s.release (0);
    EXPECT_FLOAT_EQ (s.value (0), 0.1f);   // Core's value on release (spec §5)
    EXPECT_FALSE (s.marked (0));
}

TEST (DeskState, AReleaseWithoutARelayKeepsTheHandsValue)
{
    DeskState s (3);
    s.grab (0);
    s.setFromTouch (0, 0.6f);
    s.release (0);
    EXPECT_FLOAT_EQ (s.value (0), 0.6f);
    EXPECT_TRUE (s.marked (0));
}

TEST (DeskState, ValuesStayOnTheScale)
{
    DeskState s (1);
    s.setFromTouch (0, 1.4f);
    EXPECT_FLOAT_EQ (s.value (0), 1.f);
    s.setFromPeer (0, -3.f);
    EXPECT_FLOAT_EQ (s.value (0), 0.f);
}
