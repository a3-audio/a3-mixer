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
}

TEST (DeskState, ATouchStores)
{
    DeskState s (3);
    s.setFromPeer (1, 0.2f);
    s.setFromTouch (1, 0.7f);
    EXPECT_FLOAT_EQ (s.value (1), 0.7f);
}

TEST (DeskState, ARelayAfterATouchWins)
{
    DeskState s (3);
    s.setFromTouch (1, 0.7f);
    s.setFromPeer (1, 0.3f);   // the hardware knob was touched: its position wins
    EXPECT_FLOAT_EQ (s.value (1), 0.3f);
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
}

TEST (DeskState, AReleaseWithoutARelayKeepsTheHandsValue)
{
    DeskState s (3);
    s.grab (0);
    s.setFromTouch (0, 0.6f);
    s.release (0);
    EXPECT_FLOAT_EQ (s.value (0), 0.6f);
}

TEST (DeskState, ValuesStayOnTheScale)
{
    DeskState s (1);
    s.setFromTouch (0, 1.4f);
    EXPECT_FLOAT_EQ (s.value (0), 1.f);
    s.setFromPeer (0, -3.f);
    EXPECT_FLOAT_EQ (s.value (0), 0.f);
}
