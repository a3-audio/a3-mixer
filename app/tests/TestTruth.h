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

// The cases software/tests/fixtures/make_desk_cases.py writes from the Python desk.
inline const juce::var& fixture()
{
    static const juce::var cases = juce::JSON::parse (
        juce::File (A3DESK_FIXTURES).getChildFile ("desk-cases.json").loadFileAsString());
    return cases;
}
}
