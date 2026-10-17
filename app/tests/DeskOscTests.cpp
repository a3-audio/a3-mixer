// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskControls.h"
#include "DeskOsc.h"
#include "TestTruth.h"

using namespace desk;

namespace
{
int sizeOf (const juce::var& table)
{
    const auto* object = table.getDynamicObject();
    return object != nullptr ? object->getProperties().size() : -1;
}
}

TEST (DeskControls, TheTablesAreTheHardwares)
{
    const auto& t = test::fixture()["tables"];
    for (size_t i = 0; i < channelPotKeys.size(); ++i)
        EXPECT_EQ (juce::String (channelPotKeys[i]), t["channel_pots"][juce::Identifier (juce::String ((int) i))].toString()) << i;
    for (size_t i = 0; i < masterPotKeys.size(); ++i)
        EXPECT_EQ (juce::String (masterPotKeys[i]), t["master_pots"][juce::Identifier (juce::String ((int) i))].toString()) << i;
    for (const auto& [name, key] : channelKeys)
        EXPECT_EQ (juce::String (key), t["channel_keys"][juce::Identifier (name)].toString());
    for (const auto& [key, name] : lamps)
        EXPECT_EQ (juce::String (name), t["lamps"][juce::Identifier (key)].toString());

    // The loops above only walk our tables: a row the fixture has and we lack must fail too.
    EXPECT_EQ (sizeOf (t["channel_pots"]), (int) channelPotKeys.size());
    EXPECT_EQ (sizeOf (t["master_pots"]), (int) masterPotKeys.size());
    EXPECT_EQ (sizeOf (t["channel_keys"]), (int) channelKeys.size());
    EXPECT_EQ (sizeOf (t["lamps"]), (int) lamps.size());
}

TEST (DeskControls, ItUsesTheHardwaresWordsAndNoOthers)
{
    juce::StringArray python;
    for (const auto& k : *test::fixture()["tables"]["keys_used"].getArray())
        python.add (k.toString());
    juce::StringArray ours;
    for (const auto& k : keysUsed())
        ours.addIfNotAlreadyThere (k);
    python.sort (false);
    ours.sort (false);
    EXPECT_EQ (ours.joinIntoString (" "), python.joinIntoString (" "));
}

TEST (DeskControls, EveryPotHasAnIndexAndOnlyOne)
{
    const auto& pots = allPots();
    ASSERT_EQ (pots.size(), 4u * 6u + 7u);
    for (size_t i = 0; i < pots.size(); ++i)
        EXPECT_EQ (potIndex (pots[i].key, pots[i].channel), (int) i);
    EXPECT_EQ (potIndex ("channel.gain", 5), -1);
    EXPECT_EQ (potIndex ("master.volume", 1), -1);
}

TEST (DeskControls, TheLockHoldsMasterBoothAndPhones)
{
    EXPECT_TRUE (isGuarded ("master.volume"));
    EXPECT_TRUE (isGuarded ("master.booth"));
    EXPECT_TRUE (isGuarded ("master.phones-volume"));
    EXPECT_FALSE (isGuarded ("master.phones-mix"));
    EXPECT_FALSE (isGuarded ("channel.volume"));
}

TEST (DeskOsc, TheTruthHasEverythingTheDeskNeeds)
{
    EXPECT_EQ (DeskOsc::missing (test::truth()).joinIntoString (", "), "");
}

TEST (DeskOsc, AddressesComeFromTheTruth)
{
    const DeskOsc osc (test::truth());
    EXPECT_EQ (osc.address ("channel.gain", 2), test::truth().pattern ("channel.gain").replace ("{ch}", "2"));
    EXPECT_EQ (osc.address ("master.volume"), test::truth().pattern ("master.volume"));
}

TEST (DeskOsc, EveryWordItHearsMatchesBack)
{
    const DeskOsc osc (test::truth());
    for (const auto* key : { "channel.gain", "channel.volume", "channel.cue.led", "channel.filter.led", "channel.stem",
                             "channel.stem.cursor" })
        for (int ch = 1; ch <= numChannels; ++ch)
        {
            const auto found = osc.match (osc.address (key, ch));
            ASSERT_TRUE (found.has_value()) << key << ch;
            EXPECT_EQ (found->key, key);
            EXPECT_EQ (found->number, ch);
        }
    for (const auto* key : { "master.volume", "filter.frequency", "filter.led", "aux-return.stem", "aux-return.stem.mode",
                             "aux-return.cue.led", "beat" })
        EXPECT_EQ (osc.match (osc.address (key))->key, key);
}

TEST (DeskOsc, OutOfRangeAndForeignWordsDoNotMatch)
{
    const DeskOsc osc (test::truth());
    EXPECT_FALSE (osc.match (osc.address ("channel.gain", 5)).has_value());
    EXPECT_FALSE (osc.match ("/track/1/volume").has_value());
}

TEST (DeskOsc, AnOversizedNumberFromTheNetworkIsNoMatchAndNoThrow)
{
    const DeskOsc osc (test::truth());
    const auto huge = osc.address ("channel.gain", 1).replace ("1", "99999999999999999999");
    EXPECT_NO_THROW (EXPECT_FALSE (osc.match (huge).has_value()));
}

TEST (DeskOsc, CoreAndTheClockAreOnCoresHost)
{
    const DeskOsc osc (test::truth());
    EXPECT_EQ (osc.core().host, test::truth().host ("core"));
    EXPECT_EQ (osc.core().port, test::truth().listener ("core", "osc")->port);
    EXPECT_EQ (osc.beatClock().host, test::truth().host ("core"));
    EXPECT_EQ (osc.beatClock().port, test::truth().listener ("beat-analyzer", "clock")->port);
    EXPECT_EQ (osc.ownPort(), test::truth().listener ("desk", "osc")->port);
    EXPECT_EQ (osc.vuPort(), test::truth().listener ("desk", "vu")->port);
}

TEST (DeskOsc, TheMeterThreadReadsANumberCheaply)
{
    const DeskOsc osc (test::truth());
    const auto n = test::truth().vuNumber ("main_sub");
    EXPECT_EQ (osc.vuNumberOf (osc.address ("vu", n)), n);
    EXPECT_FALSE (osc.vuNumberOf (osc.address ("vu", test::truth().vuCount() + 1)).has_value());
    EXPECT_FALSE (osc.vuNumberOf (osc.address ("channel.gain", 1)).has_value());
}
