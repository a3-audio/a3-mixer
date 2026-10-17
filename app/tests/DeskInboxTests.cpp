// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include <limits>

#include "DeskControls.h"
#include "DeskInbox.h"
#include "DeskMeters.h"
#include "TestTruth.h"
#include "VuInbox.h"

using namespace desk;

namespace
{
struct Desk
{
    DeskOsc osc { test::truth() };
    DeskState state { (int) allPots().size() };
    Indicators ind;
    StartupAsk ask;
    DeskInbox inbox { osc, state, ind, ask };

    template <typename... Args>
    void hear (const std::string& key, int number, Args... args)
    {
        juce::OSCMessage m (juce::OSCAddressPattern (osc.address (key, number)));
        (m.addArgument (juce::OSCArgument (args)), ...);
        inbox.receive (m, 1000.0);
    }
};
}

TEST (DeskInbox, ARelayedPotMovesTheKnob)
{
    Desk d;
    d.hear ("channel.gain", 2, 0.3f);
    EXPECT_FLOAT_EQ (d.state.value (potIndex ("channel.gain", 2)), 0.3f);
    d.hear ("master.booth", 0, 0.8f);
    EXPECT_FLOAT_EQ (d.state.value (potIndex ("master.booth", 0)), 0.8f);
}

TEST (DeskInbox, AnythingFromCoreIsAnAnswer)
{
    Desk d;
    EXPECT_FALSE (d.ask.joined());
    d.hear ("beat", 0, 1, 1, 120.f);
    EXPECT_TRUE (d.ask.joined());
}

TEST (DeskInbox, LampsLightTheKeys)
{
    Desk d;
    d.hear ("channel.cue.led", 2, 1.f);
    d.hear ("channel.filter.led", 4, 1.f);
    EXPECT_TRUE (d.ind.cue[1]);
    EXPECT_TRUE (d.ind.fx[3]);
    d.hear ("channel.cue.led", 2, 0.f);
    EXPECT_FALSE (d.ind.cue[1]);
}

TEST (DeskInbox, TheFilterLampPicksHpfOrLpf)
{
    Desk d;
    d.hear ("filter.led", 0, juce::String ("high_pass"));
    EXPECT_EQ (d.ind.highPass, std::optional<bool> (true));
    d.hear ("filter.led", 0, juce::String ("nonsense"));
    EXPECT_EQ (d.ind.highPass, std::optional<bool> (true));
}

TEST (DeskInbox, StemsCursorAndReturn)
{
    Desk d;
    d.hear ("channel.stem", 3, 0b100);
    d.hear ("channel.stem.cursor", 3, 7);
    d.hear ("aux-return.stem", 0, 2, 0, 1, 0, 0, 0, 0, 0, 0);
    d.hear ("aux-return.stem.mode", 0, 0);
    d.hear ("aux-return.cue.led", 0, 1.f);
    EXPECT_EQ (d.ind.stemMask[2], 0b100);
    EXPECT_EQ (d.ind.cursor[2], 7);
    EXPECT_EQ (d.ind.returnCursor, 2);
    EXPECT_EQ (d.ind.returnMode, 0);
    EXPECT_TRUE (d.ind.returnCue);
}

TEST (DeskInbox, TheBeatFlashesTapAndCarriesTheTempo)
{
    Desk d;
    d.hear ("beat", 0, 1, 1, 124.f);
    EXPECT_DOUBLE_EQ (d.ind.tapLitUntilMs, 1000.0 + tapFlashMs);
    EXPECT_FLOAT_EQ (d.ind.bpm, 124.f);
}

TEST (DeskInbox, DamagedMessagesChangeNothing)
{
    Desk d;
    d.hear ("channel.stem", 1, juce::String ("x"));
    d.hear ("channel.stem.cursor", 1, 9);
    d.hear ("aux-return.stem", 0, 1, 0, 1);
    EXPECT_EQ (d.ind.stemMask[0], 0);
    EXPECT_EQ (d.ind.cursor[0], 0);
    EXPECT_EQ (d.ind.returnCursor, 1);
}

TEST (DeskInbox, ANonFiniteValueIsDropped)
{
    Desk d;
    d.hear ("channel.gain", 2, 0.3f);
    d.hear ("channel.gain", 2, std::numeric_limits<float>::quiet_NaN());
    d.hear ("channel.gain", 2, std::numeric_limits<float>::infinity());
    EXPECT_FLOAT_EQ (d.state.value (potIndex ("channel.gain", 2)), 0.3f);
    d.hear ("beat", 0, 1, 1, std::numeric_limits<float>::quiet_NaN());
    EXPECT_FLOAT_EQ (d.ind.bpm, 0.f);
}

TEST (VuInbox, IgnoresNonFinitePeaks)
{
    VuInbox vu (4);
    vu.note (1, std::numeric_limits<float>::quiet_NaN());
    vu.note (2, std::numeric_limits<float>::infinity());
    const auto taken = vu.take();
    ASSERT_EQ (taken.size(), 4u);
    EXPECT_FALSE (taken[0].has_value());
    EXPECT_FALSE (taken[1].has_value());
}

TEST (VuInbox, KeepsTheLoudestSinceTheLastTake)
{
    VuInbox vu (66);
    vu.note (5, 0.2f);
    vu.note (5, 0.6f);
    vu.note (5, 0.1f);
    vu.note (70, 1.f);
    const auto taken = vu.take();
    ASSERT_EQ (taken.size(), 66u);
    EXPECT_FLOAT_EQ (*taken[4], 0.6f);
    EXPECT_FALSE (taken[0].has_value());
    EXPECT_FALSE (vu.take()[4].has_value());
}

TEST (DeskMeters, AChannelShowsItsLouderSide)
{
    const DeskOsc osc (test::truth());
    DeskMeters meters (osc, test::truth().meterBallistics());
    std::vector<std::optional<float>> peaks ((size_t) test::truth().vuCount());
    peaks[(size_t) osc.vuNumber ("in2_pre_L") - 1] = 0.1f;
    peaks[(size_t) osc.vuNumber ("in2_pre_R") - 1] = 0.5f;
    peaks[(size_t) osc.vuNumber ("main_top3") - 1] = 0.25f;
    peaks[(size_t) osc.vuNumber ("stem_b1") - 1] = 0.75f;
    meters.take (peaks, 1000);
    EXPECT_NEAR (meters.channelInput (2, 1000).bar, 0.5f, 1e-4f);
    EXPECT_NEAR (meters.output (3, 1000).bar, 0.25f, 1e-4f);
    EXPECT_NEAR (meters.stem (4, 1000).bar, 0.75f, 1e-4f);
    EXPECT_FLOAT_EQ (meters.takenPeak ("in2_pre_R"), 0.5f);
    meters.take (std::vector<std::optional<float>> ((size_t) test::truth().vuCount(), 0.f), 1040);
    EXPECT_LT (meters.channelInput (2, 3000).bar, 0.5f);   // falls on its own clock
}

TEST (DeskMeters, AnalogAndReturnMetersReadTheirOwnNames)
{
    const DeskOsc osc (test::truth());
    DeskMeters meters (osc, test::truth().meterBallistics());
    std::vector<std::optional<float>> peaks ((size_t) test::truth().vuCount());
    peaks[(size_t) osc.vuNumber ("analog3_R") - 1] = 0.4f;
    peaks[(size_t) osc.vuNumber ("stem_aux_R") - 1] = 0.6f;
    peaks[(size_t) osc.vuNumber ("aux_L") - 1] = 0.8f;
    meters.take (peaks, 1000);
    EXPECT_NEAR (meters.analog (3, 1000).bar, 0.4f, 1e-4f);
    EXPECT_NEAR (meters.returnStem (1000).bar, 0.6f, 1e-4f);
    EXPECT_NEAR (meters.returnAnalog (1000).bar, 0.8f, 1e-4f);
    EXPECT_FLOAT_EQ (meters.analog (1, 1000).bar, 0.f);
}

// The clip hatch's peaks, by the same names and the same louder side as the bars.
TEST (DeskMeters, TheClipPeaksReadTheBarsNames)
{
    const DeskOsc osc (test::truth());
    DeskMeters meters (osc, test::truth().meterBallistics());
    std::vector<std::optional<float>> peaks ((size_t) test::truth().vuCount());
    for (const auto* name : { "stem_b2", "analog3_L", "analog3_R", "stem_aux_L", "aux_R" })
        ASSERT_GT (osc.vuNumber (name), 0) << name;
    peaks[(size_t) osc.vuNumber ("stem_b2") - 1] = 1.2f;
    peaks[(size_t) osc.vuNumber ("analog3_L") - 1] = 0.3f;
    peaks[(size_t) osc.vuNumber ("analog3_R") - 1] = 1.1f;
    peaks[(size_t) osc.vuNumber ("stem_aux_L") - 1] = 1.3f;
    peaks[(size_t) osc.vuNumber ("aux_R") - 1] = 1.4f;
    meters.take (peaks, 1000);
    EXPECT_FLOAT_EQ (meters.stemPeak (5), 1.2f);
    EXPECT_FLOAT_EQ (meters.stemPeak (0), 0.f);
    EXPECT_FLOAT_EQ (meters.analogPeak (3), 1.1f);
    EXPECT_FLOAT_EQ (meters.returnStemPeak(), 1.3f);
    EXPECT_FLOAT_EQ (meters.returnAnalogPeak(), 1.4f);
}
