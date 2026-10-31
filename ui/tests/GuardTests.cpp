// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "shared/OscSendGuard.h"

// The runner refuses every OSC sender before the first test (a3-motion-ui
// #67): a test that aims one anywhere -- the truth names the live Core --
// fails instead of moving the room.
TEST (Guard, TheRunnerRefusesEverySender)
{
    juce::OSCSender sender;
    EXPECT_THROW (a3::connectOscSender (sender, "192.0.2.1", 1), std::logic_error);
}

TEST (Guard, ASenderOnTheDesksOwnSocketIsRefusedToo)
{
    juce::DatagramSocket socket (false);
    juce::OSCSender sender;
    EXPECT_THROW (a3::connectOscSenderToSocket (sender, socket, "192.0.2.1", 1), std::logic_error);
}
