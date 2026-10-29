// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cmath>

#include <gtest/gtest.h>

#include "DeskComponent.h"
#include "DeskLink.h"
#include "TestTruth.h"

using namespace desk;

namespace
{
// The rig's screen: the desk runs fullscreen there.
constexpr int rigWidth = 768, rigHeight = 1024;
constexpr double stepMs = 1000.0 / 25.0;

float linear (double db) { return static_cast<float> (std::pow (10.0, db / 20.0)); }

struct ChannelLook
{
    float fader, trim, high, mid, low, send;
    bool cue, fx;
    double peakDb, burstDb;   // the steady peak and an earlier one the hold line still stands on
};

// A product photo's mixer: four channels playing, nothing at an end stop.
constexpr std::array<ChannelLook, numChannels> channels { {
    { 0.86f, 0.56f, 0.50f, 0.47f, 0.36f, 0.12f, false, false, -8.0, -7.0 },
    { 0.80f, 0.60f, 0.62f, 0.52f, 0.50f, 0.22f, true, false, -10.0, -8.0 },
    { 0.90f, 0.53f, 0.48f, 0.55f, 0.52f, 0.08f, false, true, -5.5, -4.0 },
    { 0.76f, 0.58f, 0.53f, 0.50f, 0.46f, 0.15f, false, false, -11.0, -9.5 },
} };

struct MasterLook
{
    const char* key;
    float value;
};

constexpr std::array<MasterLook, 7> master { {
    { "master.volume", 0.71f },      // two o'clock
    { "master.booth", 0.40f },       // eleven
    { "master.phones-volume", 0.55f },
    { "master.phones-mix", 0.50f },
    { "master.aux-return", 0.42f },
    { "filter.frequency", 0.46f },
    { "filter.resonance", 0.30f },
} };

// SUB, then tops 1-7: the room's outputs a little under the loudest channel.
constexpr std::array<double, 8> outputDb { -15.0, -17.0, -16.5, -19.0, -18.0, -21.0, -20.0, -22.5 };
constexpr std::array<double, 4> deckDb { -9.0, -11.0, -6.5, -10.5 };   // deck_a ... deck_d
constexpr double returnDb = -16.0;

void say (DeskComponent& desk, const juce::String& address, float value, double nowMs)
{
    desk.receive (juce::OSCMessage (juce::OSCAddressPattern (address), value), nowMs);
}

void sayInt (DeskComponent& desk, const juce::String& address, int value, double nowMs)
{
    desk.receive (juce::OSCMessage (juce::OSCAddressPattern (address), value), nowMs);
}

/** Everything Core relays and announces to a desk while four decks play, as Core would send it. */
void tellTheMix (DeskComponent& desk, double nowMs)
{
    const auto& osc = *desk.osc();
    for (int ch = 1; ch <= numChannels; ++ch)
    {
        const auto& c = channels[(size_t) ch - 1];
        say (desk, osc.address ("channel.volume", ch), c.fader, nowMs);
        say (desk, osc.address ("channel.gain", ch), c.trim, nowMs);
        say (desk, osc.address ("channel.eq.high", ch), c.high, nowMs);
        say (desk, osc.address ("channel.eq.mid", ch), c.mid, nowMs);
        say (desk, osc.address ("channel.eq.low", ch), c.low, nowMs);
        say (desk, osc.address ("channel.aux-send", ch), c.send, nowMs);
        say (desk, osc.address ("channel.cue.led", ch), c.cue ? 1.f : 0.f, nowMs);
        say (desk, osc.address ("channel.filter.led", ch), c.fx ? 1.f : 0.f, nowMs);
        if (osc.hasOptional ("channel.source"))
        {
            sayInt (desk, osc.address ("channel.source", ch), ch, nowMs);   // deck A on CH 1 ... deck D on CH 4
            sayInt (desk, osc.address ("channel.source.cursor", ch), ch, nowMs);
        }
        if (osc.hasOptional ("stemdeck.present"))
            sayInt (desk, osc.address ("stemdeck.present", ch), 1, nowMs);
    }
    for (const auto& m : master)
        say (desk, osc.address (m.key), m.value, nowMs);
    desk.receive (juce::OSCMessage (juce::OSCAddressPattern (osc.address ("filter.led")), juce::String ("high_pass")),
                  nowMs);
}

void notePair (VuInbox& vu, const DeskOsc& osc, const std::string& left, const std::string& right, double db)
{
    vu.note (osc.vuNumber (left.c_str()), linear (db));
    vu.note (osc.vuNumber (right.c_str()), linear (db - 0.8));
}

/** One frame of peaks as the engine's meters would send them: `burst` adds each channel's louder earlier peak. */
void notePeaks (DeskComponent& desk, bool burst)
{
    auto& vu = *desk.vuInbox();
    const auto& osc = *desk.osc();
    for (int ch = 1; ch <= numChannels; ++ch)
    {
        const auto& c = channels[(size_t) ch - 1];
        const auto in = "in" + std::to_string (ch) + "_pre";
        notePair (vu, osc, in + "_L", in + "_R", burst ? c.burstDb : c.peakDb);
        notePair (vu, osc, "analog" + std::to_string (ch) + "_L", "analog" + std::to_string (ch) + "_R", -60.0);
    }
    const char* outputs[] { "main_sub", "main_top1", "main_top2", "main_top3", "main_top4", "main_top5", "main_top6", "main_top7" };
    for (size_t i = 0; i < outputDb.size(); ++i)
        vu.note (osc.vuNumber (outputs[i]), linear (outputDb[i] + (burst ? 2.5 : 0.0)));
    const char* decks[] { "deck_a", "deck_b", "deck_c", "deck_d" };
    for (size_t i = 0; i < deckDb.size(); ++i)
        vu.note (osc.vuNumber (decks[i]), linear (deckDb[i] + (burst ? 2.0 : 0.0)));
    notePair (vu, osc, "aux_L", "aux_R", returnDb);
}
}

// For the website: with A3_DESK_SNAPSHOT_DIR set, the desk at the rig's size in
// a product photo's state -- joined to a Core, four decks playing, meters lit --
// as desk-promo.png. Everything arrives through the desk's own inbox and meter
// inbox, as Core would send it; nothing goes on a network.
TEST (DeskPromo, WritesThePlayingDeskForReview)
{
    const auto directory = juce::SystemStats::getEnvironmentVariable ("A3_DESK_SNAPSHOT_DIR", {});
    if (directory.isEmpty())
        GTEST_SKIP() << "A3_DESK_SNAPSHOT_DIR not set";

    std::vector<Outgoing> sent;
    DeskComponent desk ([&sent] (const Outgoing& out) { sent.push_back (out); return true; });
    desk.setSize (rigWidth, rigHeight);
    desk.useTruth (test::truth());
    ASSERT_NE (desk.osc(), nullptr) << desk.statusText();
    desk.setLinkState (DeskLink::Opened::ok);
    desk.announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-1" }, 0);
    desk.step (0);

    double now = 100.0;
    desk.receive (juce::OSCMessage (juce::OSCAddressPattern (desk.osc()->address ("beat")), 1, 1, 126.f), now);
    tellTheMix (desk, now);
    desk.step (now);

    // A louder beat, then a second of steady playing: the bars settle, the hold lines still stand above them.
    notePeaks (desk, true);
    desk.step (now += stepMs);
    for (int i = 0; i < 25; ++i)
    {
        notePeaks (desk, false);
        desk.step (now += stepMs);
    }
    ASSERT_TRUE (desk.handsAccepted()) << desk.statusText();
    EXPECT_TRUE (desk.statusText().contains ("truth ok")) << desk.statusText();

    const auto file = juce::File (directory).getChildFile ("desk-promo.png");
    ASSERT_TRUE (file.getParentDirectory().createDirectory().wasOk());
    file.deleteFile();
    juce::FileOutputStream stream (file);
    ASSERT_TRUE (stream.openedOk());
    ASSERT_TRUE (juce::PNGImageFormat().writeImageToStream (desk.createComponentSnapshot (desk.getLocalBounds()), stream));
}
