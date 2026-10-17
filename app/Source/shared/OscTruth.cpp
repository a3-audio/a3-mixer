// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "OscTruth.h"

#include <juce_cryptography/juce_cryptography.h>

#include "TruthKeeper.h"

namespace a3
{
juce::String OscTruth::host (const juce::String& name) const
{
    return _data["hosts"][juce::Identifier (name)].toString();
}

std::optional<OscTruth::Listener> OscTruth::listener (const juce::String& program, const juce::String& role) const
{
    if (const auto* listeners = _data["listeners"].getArray())
        for (const auto& entry : *listeners)
            if (entry["program"].toString() == program && entry["role"].toString() == role)
                return Listener { entry["host"].toString(), static_cast<int> (entry["port"]) };
    return std::nullopt;
}

bool OscTruth::hasAddress (const juce::String& key) const
{
    return _data["addresses"].hasProperty (juce::Identifier (key));
}

juce::String OscTruth::pattern (const juce::String& key) const
{
    return _data["addresses"][juce::Identifier (key)]["pattern"].toString();
}

std::pair<int, int> OscTruth::range (const juce::String& key, const juce::String& field) const
{
    const auto bounds = _data["addresses"][juce::Identifier (key)][juce::Identifier (field)];
    if (const auto* pair = bounds.getArray(); pair != nullptr && pair->size() == 2)
        return { static_cast<int> (pair->getReference (0)), static_cast<int> (pair->getReference (1)) };
    return { 0, -1 };
}

int OscTruth::vuNumber (const juce::String& meterName) const
{
    if (const auto* meters = _data["vu_meters"].getArray())
        for (int i = 0; i < meters->size(); ++i)
            if (meters->getReference (i).toString() == meterName)
                return i + 1;
    return 0;
}

int OscTruth::vuCount() const
{
    const auto* meters = _data["vu_meters"].getArray();
    return meters != nullptr ? meters->size() : 0;
}

namespace
{
float numberOr (const juce::var& block, const char* key, float fallback)
{
    const auto value = block[juce::Identifier (key)];
    return block.hasProperty (juce::Identifier (key)) && (value.isInt() || value.isInt64() || value.isDouble())
               ? static_cast<float> (value)
               : fallback;
}

juce::String digestOf (const juce::MemoryBlock& bytes)
{
    return juce::SHA256 (bytes).toHexString();
}
}

MeterBallisticsParameters OscTruth::meterBallistics() const
{
    const MeterBallisticsParameters defaults;
    const auto block = _data["meters"];
    if (! block.isObject())
        return defaults;
    return { numberOr (block, "attack_ms", defaults.attackMs),
             numberOr (block, "release_db_per_second", defaults.releaseDbPerSecond),
             numberOr (block, "peak_hold_seconds", defaults.peakHoldSeconds) };
}

OscTruth parseOscTruth (const juce::String& json)
{
    OscTruth truth;
    const auto result = juce::JSON::parse (json, truth._data);
    if (result.failed())
        truth._error = "a3-osc.json does not parse: " + result.getErrorMessage();
    // juce::var counts an array as an object too.
    else if (! truth._data.isObject() || truth._data.isArray())
        truth._error = "a3-osc.json is not an object";
    return truth;
}

OscTruth loadOscTruth (const juce::File& file)
{
    if (! file.existsAsFile())
    {
        OscTruth truth;
        truth._error = "no OSC truth at " + file.getFullPathName();
        return truth;
    }
    juce::MemoryBlock bytes;
    file.loadFileAsData (bytes);
    auto truth = parseOscTruth (bytes.toString());
    truth._digest = digestOf (bytes);
    return truth;
}

juce::File oscTruthFileFrom (const char* override, const juce::File& home,
                             const std::function<bool (const juce::String&)>& usable)
{
    const auto cache = truthkeeper::cachePath (home.getFullPathName().toStdString());
    const juce::File cached (cache);
    const auto cacheUsable = cached.existsAsFile() && usable (cached.loadFileAsString());
    return juce::File (truthkeeper::startPath (override, cache, cacheUsable, "/usr/share/a3/a3-osc.json"));
}

juce::File oscTruthFile (const std::function<bool (const juce::String&)>& usable)
{
    const auto given = juce::SystemStats::getEnvironmentVariable ("A3_OSC_TRUTH", {});
    return oscTruthFileFrom (given.isNotEmpty() ? given.toRawUTF8() : nullptr,
                             juce::File::getSpecialLocation (juce::File::userHomeDirectory), usable);
}
}
