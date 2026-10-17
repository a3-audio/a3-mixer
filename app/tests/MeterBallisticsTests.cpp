// SPDX-FileCopyrightText: 2023 Patric Schmitz
//
// SPDX-License-Identifier: GPL-3.0-or-later

/*

  A3 Motion UI
  Copyright (C) 2023 Patric Schmitz

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.

*/


#include <gtest/gtest.h>

#include "shared/MeterBallistics.h"

#include <cmath>

using namespace a3;

namespace
{
float
db (float amplitude)
{
  return 20.f * std::log10 (amplitude);
}

float
amplitude (float decibels)
{
  return std::pow (10.f, decibels / 20.f);
}
}

// The numbers decided on 2026-10-07 (.claude/notes/meter-ballistics.md) for
// every meter in the system: the desk, StemDeck and Motion. A truth without a
// "meters" block falls back on these, so they are the rule, not a guess.
TEST (MeterBallistics, TheDefaultsAreTheSharedRule)
{
  MeterBallisticsParameters const defaults;
  EXPECT_FLOAT_EQ (defaults.attackMs, 0.f);
  EXPECT_FLOAT_EQ (defaults.releaseDbPerSecond, 20.f);
  EXPECT_FLOAT_EQ (defaults.peakHoldSeconds, 1.5f);
}

TEST (MeterBallistics, NothingNotedIsSilence)
{
  MeterBallistics meter;
  EXPECT_FLOAT_EQ (meter.bar (0), 0.f);
  EXPECT_FLOAT_EQ (meter.hold (0), 0.f);
  EXPECT_FLOAT_EQ (meter.bar (100000), 0.f);
}

TEST (MeterBallistics, APeakShowsAtOnce)
{
  MeterBallistics meter;
  meter.note (0.5f, 1000);
  EXPECT_FLOAT_EQ (meter.bar (1000), 0.5f);
  EXPECT_FLOAT_EQ (meter.hold (1000), 0.5f);
}

// The analyzer sends raw peaks: silence after a hit arrives as 0 on the very
// next tick. The bar falls from the hit instead, 20 dB a second.
TEST (MeterBallistics, TheBarFallsTwentyDecibelsASecond)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (0.f, 1040);

  EXPECT_NEAR (db (meter.bar (1040)), 0.f, 0.01f);
  EXPECT_NEAR (db (meter.bar (1540)), -10.f, 0.01f);
  EXPECT_NEAR (db (meter.bar (2040)), -20.f, 0.01f);
}

// A steady sound is a steady bar: it falls toward the latest peak, not past it.
TEST (MeterBallistics, TheBarNeverFallsBelowTheLatestPeak)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (amplitude (-12.f), 1040);
  EXPECT_NEAR (db (meter.bar (5000)), -12.f, 0.01f);
}

// A falling bar caught by a new, louder peak jumps to it.
TEST (MeterBallistics, ALouderPeakInterruptsTheFall)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (0.f, 1040);
  meter.note (amplitude (-3.f), 1540);
  EXPECT_NEAR (db (meter.bar (1540)), -3.f, 0.01f);
}

TEST (MeterBallistics, TheHoldStandsOneAndAHalfSecondsThenFallsTwentyDecibelsASecond)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (0.f, 1040);

  EXPECT_NEAR (db (meter.hold (2000)), 0.f, 0.01f);
  EXPECT_NEAR (db (meter.hold (2500)), 0.f, 0.01f);
  EXPECT_NEAR (db (meter.hold (3000)), -10.f, 0.01f);
  EXPECT_GT (meter.hold (3000), meter.bar (3000))
      << "the hold line fell into the bar";
}

TEST (MeterBallistics, ALouderPeakRestartsTheHold)
{
  MeterBallistics meter;
  meter.note (0.5f, 1000);
  meter.note (1.f, 1200);
  meter.note (0.f, 1240);
  EXPECT_NEAR (db (meter.hold (2700)), 0.f, 0.01f);
}

TEST (MeterBallistics, AQuieterPeakLeavesTheHoldRunning)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (0.5f, 2000);
  EXPECT_NEAR (db (meter.hold (2600)), -2.f, 0.01f);
}

// Once the falling hold reaches the bar it rides on its top rather than
// vanishing under the fill.
TEST (MeterBallistics, TheHoldNeverStandsBelowTheBar)
{
  MeterBallistics meter;
  meter.note (1.f, 1000);
  meter.note (amplitude (-6.f), 1040);
  EXPECT_NEAR (db (meter.hold (10000)), -6.f, 0.01f);
  EXPECT_FLOAT_EQ (meter.hold (10000), meter.bar (10000));
}

// Core's truth sets the numbers; the meter takes what it is given.
TEST (MeterBallistics, TakesItsParameters)
{
  MeterBallistics meter ({ 0.f, 40.f, 0.5f });
  meter.note (1.f, 1000);
  meter.note (0.f, 1001);

  EXPECT_NEAR (db (meter.bar (1501)), -20.f, 0.01f);
  EXPECT_NEAR (db (meter.hold (1500)), 0.f, 0.01f);
  EXPECT_NEAR (db (meter.hold (2000)), -20.f, 0.01f);
}

TEST (MeterBallistics, AnAttackTimeRisesOverThatTime)
{
  MeterBallistics meter ({ 100.f, 20.f, 1.5f });
  meter.note (amplitude (-20.f), 1000);
  meter.note (1.f, 2000);

  EXPECT_NEAR (db (meter.bar (2050)), -10.f, 0.01f);
  EXPECT_NEAR (db (meter.bar (2100)), 0.f, 0.01f);
}

TEST (MeterBallistics, NewParametersApplyToTheNextFall)
{
  MeterBallistics meter;
  meter.setParameters ({ 0.f, 40.f, 1.5f });
  meter.note (1.f, 1000);
  meter.note (0.f, 1001);
  EXPECT_NEAR (db (meter.bar (1501)), -20.f, 0.01f);
}

// A nonsense number from the wire is silence, not a stuck meter.
TEST (MeterBallistics, ANonsensePeakIsSilence)
{
  MeterBallistics meter;
  meter.note (std::nanf (""), 1000);
  EXPECT_FLOAT_EQ (meter.bar (1000), 0.f);
  meter.note (-1.f, 1040);
  EXPECT_FLOAT_EQ (meter.bar (1040), 0.f);
}
