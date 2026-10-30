// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <optional>
#include <regex>
#include <string>
#include <vector>

#include "shared/OscTruth.h"

namespace desk
{
struct Endpoint
{
    juce::String host;
    int port = -1;
};

struct Match
{
    std::string key;
    int number = 0;   // {ch} or {n}; 0 for an address without one
};

/** The desk's words, ports and hosts, out of the one truth. A fact the truth
    does not have is a missing key, never a default (a default is a second truth). */
class DeskOsc
{
public:
    explicit DeskOsc (a3::OscTruth truth);

    static juce::StringArray missing (const a3::OscTruth& truth);

    const a3::OscTruth& truth() const { return _truth; }
    juce::String address (const std::string& key, int number = 0) const;
    /** What a message from Core is, for the words the desk hears; nullopt for any other. */
    std::optional<Match> match (const juce::String& address) const;
    /** The n of /vu/<n> in range, without a regex: the meter thread asks this ~2500 times a second. */
    std::optional<int> vuNumberOf (const juce::String& address) const;
    /** Seen from the desk, a listener on every interface ("any") is on Core's machine. */
    Endpoint core() const;
    Endpoint beatClock() const;
    int ownPort() const;
    int vuPort() const;
    /** A word an older Core's truth may lack: its absence is no missing key, the feature just is not offered. */
    bool hasOptional (const std::string& key) const;
    /** All of the delay list's words (a3_mixer_osc.has_delay_page): without them SELECT only cues (R25). */
    bool hasDelayList() const;
    int vuNumber (const char* meterName) const { return _truth.vuNumber (meterName); }

private:
    struct Matcher
    {
        std::string key;
        std::regex regex;
        std::pair<int, int> range;   // {0, -1}: no number in the address
    };

    Endpoint onTheCoreMachine (const char* program, const char* role) const;

    a3::OscTruth _truth;
    std::vector<Matcher> _matchers;
    juce::String _vuPrefix;
};
}
