// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>
#include <juce_events/juce_events.h>

#include "shared/OscSendGuard.h"

int main (int argc, char** argv)
{
    // First, before any test: no sender may be aimed anywhere (a3-motion-ui #67).
    a3::refuseOscSenders();
    ::testing::InitGoogleTest (&argc, argv);
    // This thread is the message thread: the paint tests run on it, synchronously.
    juce::ScopedJuceInitialiser_GUI juce;
    return RUN_ALL_TESTS();
}
