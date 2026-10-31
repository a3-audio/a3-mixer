// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <functional>
#include <optional>
#include <utility>

#include <juce_core/juce_core.h>

#include "MeterBallistics.h"

namespace a3
{
/** The one truth, a3-core's a3-osc.json, read (vendored from a3-motion-ui's
    OscTruth, issue: extract into a3-osc-cpp). The desk resolves where a
    listener is itself (DeskOsc): seen from the desk, "any" is Core's host. */
class OscTruth
{
public:
    struct Listener
    {
        juce::String host;
        int port = -1;
    };

    bool isValid() const { return _error.isEmpty(); }
    const juce::String& error() const { return _error; }
    const juce::String& digest() const { return _digest; }

    juce::String host (const juce::String& name) const;
    std::optional<Listener> listener (const juce::String& program, const juce::String& role) const;
    bool hasAddress (const juce::String& key) const;
    juce::String pattern (const juce::String& key) const;
    /** An address field's allowed numbers, e.g. {1, 4} for "ch"; {0, -1} for none. */
    std::pair<int, int> range (const juce::String& key, const juce::String& field) const;
    /** /vu/<n> of a meter by name, 1-based; 0 for none. */
    int vuNumber (const juce::String& meterName) const;
    int vuCount() const;
    MeterBallisticsParameters meterBallistics() const;

private:
    friend OscTruth parseOscTruth (const juce::String& json);
    friend OscTruth loadOscTruth (const juce::File& file);

    juce::var _data;
    juce::String _error;
    juce::String _digest;
};

OscTruth parseOscTruth (const juce::String& json);
OscTruth loadOscTruth (const juce::File& file);

/** $A3_OSC_TRUTH as given, else the cache Core last served if `usable`
    says it reads, else the package's file (absent on a machine without
    a3-core: the desk then waits for Core's announcement). */
juce::File oscTruthFileFrom (const char* override, const juce::File& home,
                             const std::function<bool (const juce::String&)>& usable);
juce::File oscTruthFile (const std::function<bool (const juce::String&)>& usable);
}
