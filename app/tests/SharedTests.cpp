// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "TestTruth.h"
#include "shared/TruthKeeper.h"
#include "shared/TruthKeeperLink.h"

namespace tk = a3::truthkeeper;

TEST (TestTruth, IsTheOfflineCopy)
{
    ASSERT_TRUE (desk::test::truth().isValid()) << desk::test::truth().error();
    EXPECT_TRUE (desk::test::truth().host ("core").startsWith ("192.0.2."));
    EXPECT_EQ (desk::test::truth().digest().length(), 64);
}

TEST (OscTruth, NamesTheDesksListeners)
{
    const auto osc = desk::test::truth().listener ("desk", "osc");
    const auto vu = desk::test::truth().listener ("desk", "vu");
    ASSERT_TRUE (osc.has_value());
    ASSERT_TRUE (vu.has_value());
    EXPECT_EQ (osc->host, "any");
    EXPECT_GT (osc->port, 0);
    EXPECT_NE (osc->port, vu->port);
}

TEST (OscTruth, KnowsAnAddressItsPatternAndItsRange)
{
    const auto& t = desk::test::truth();
    EXPECT_TRUE (t.hasAddress ("channel.gain"));
    EXPECT_FALSE (t.hasAddress ("channel.no-such-word"));
    EXPECT_TRUE (t.pattern ("channel.gain").contains ("{ch}"));
    EXPECT_EQ (t.range ("channel.gain", "ch"), std::make_pair (1, 4));
    EXPECT_EQ (t.range ("master.volume", "ch"), std::make_pair (0, -1));
}

TEST (OscTruth, FindsAMeterByName)
{
    const auto& t = desk::test::truth();
    EXPECT_GT (t.vuNumber ("main_sub"), 0);
    EXPECT_EQ (t.vuNumber ("no_such_meter"), 0);
    EXPECT_GE (t.vuCount(), t.vuNumber ("in4_post_R"));
}

TEST (OscTruth, AGarbageFileIsNotATruth)
{
    EXPECT_FALSE (a3::parseOscTruth ("{ nope").isValid());
    EXPECT_FALSE (a3::parseOscTruth ("[1, 2]").isValid());
}

TEST (OscTruth, StartsOnTheOverrideThenTheCacheThenThePackage)
{
    const auto home = juce::File::createTempFile ("desk-home");
    home.createDirectory();
    const auto usable = [] (const juce::String& text) { return a3::parseOscTruth (text).isValid(); };
    EXPECT_EQ (a3::oscTruthFileFrom ("/x/given.json", home, usable).getFullPathName(), "/x/given.json");
    EXPECT_EQ (a3::oscTruthFileFrom (nullptr, home, usable).getFullPathName(), "/usr/share/a3/a3-osc.json");
    const juce::File cache (tk::cachePath (home.getFullPathName().toStdString()));
    cache.getParentDirectory().createDirectory();
    cache.replaceWithText ("{\"hosts\": {}}");
    EXPECT_EQ (a3::oscTruthFileFrom (nullptr, home, usable), cache);
    home.deleteRecursively();
}

// Copied from a3-motion-ui's TruthKeeper tests: the same decisions.
TEST (TruthKeeper, TwoOrThreeStringsAreAnAnnouncement)
{
    EXPECT_FALSE (tk::announcementSize (1));
    EXPECT_TRUE (tk::announcementSize (2));
    EXPECT_TRUE (tk::announcementSize (3));
    EXPECT_FALSE (tk::announcementSize (4));
}

TEST (TruthKeeper, TheSameFingerprintNeedsNoFetch)
{
    EXPECT_FALSE (tk::needsFetch ("abc", "abc"));
    EXPECT_TRUE (tk::needsFetch ("abc", "abd"));
}

TEST (TruthKeeper, BodyHeaderAndAnnouncementMustAgree)
{
    EXPECT_TRUE (tk::verified ("h", "h", "h"));
    EXPECT_FALSE (tk::verified ("h", "h", "x"));
    EXPECT_FALSE (tk::verified ("", "", ""));
}

TEST (Announcement, ReadsUrlFingerprintAndBootId)
{
    const juce::OSCMessage three (juce::OSCAddressPattern (tk::announceAddress), juce::String ("http://x/a3-osc.json"),
                                  juce::String ("f1"), juce::String ("b1"));
    const auto read = a3::readAnnouncement (three);
    ASSERT_TRUE (read.has_value());
    EXPECT_EQ (read->fingerprint, "f1");
    EXPECT_EQ (read->bootId, "b1");

    const juce::OSCMessage two (juce::OSCAddressPattern (tk::announceAddress), juce::String ("u"), juce::String ("f1"));
    ASSERT_TRUE (a3::readAnnouncement (two).has_value());
    EXPECT_TRUE (a3::readAnnouncement (two)->bootId.isEmpty());

    const juce::OSCMessage wrong (juce::OSCAddressPattern ("/elsewhere"), juce::String ("u"), juce::String ("f"));
    EXPECT_FALSE (a3::readAnnouncement (wrong).has_value());
}
