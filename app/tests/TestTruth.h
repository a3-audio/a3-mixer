// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <juce_core/juce_core.h>

#include "shared/OscTruth.h"

namespace desk::test
{
// The truth test.sh hands over: an offline copy of a3-core's, every named
// host moved to 192.0.2.x. Never a literal address in a test: the truth is
// the one place that says them.
inline const a3::OscTruth& truth()
{
    static const a3::OscTruth loaded = a3::loadOscTruth (
        juce::File (juce::SystemStats::getEnvironmentVariable ("A3_OSC_TRUTH", {})));
    return loaded;
}

// The truth with pro-DJ LIVE in it, or without: the word is optional for the desk, so its tests
// run the same against a Core's truth that has it and one that does not.
inline a3::OscTruth truthWithLive (bool with)
{
    auto data = juce::JSON::parse (juce::File (juce::SystemStats::getEnvironmentVariable ("A3_OSC_TRUTH", {}))
                                       .loadFileAsString());
    auto* addresses = data["addresses"].getDynamicObject();
    if (addresses == nullptr)
        return a3::parseOscTruth (juce::JSON::toString (data));
    if (! with)
        addresses->removeProperty ("prodj.live");
    else if (! addresses->hasProperty ("prodj.live"))
    {
        auto* word = new juce::DynamicObject();
        word->setProperty ("pattern", "/prodj/live");
        word->setProperty ("args", "i");
        addresses->setProperty ("prodj.live", juce::var (word));
    }
    return a3::parseOscTruth (juce::JSON::toString (data));
}

// The cases software/tests/fixtures/make_desk_cases.py writes from the Python desk.
inline const juce::var& fixture()
{
    static const juce::var cases = juce::JSON::parse (
        juce::File (A3DESK_FIXTURES).getChildFile ("desk-cases.json").loadFileAsString());
    return cases;
}
}
