// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskControls.h"

#include <map>

namespace desk
{
const std::vector<Pot>& allPots()
{
    static const std::vector<Pot> pots = [] {
        std::vector<Pot> made;
        for (int ch = 1; ch <= numChannels; ++ch)
            for (const auto& key : channelPotKeys)
                made.push_back ({ key, ch });
        for (const auto& key : masterPotKeys)
            made.push_back ({ key, 0 });
        return made;
    }();
    return pots;
}

int potIndex (const std::string& key, int channel)
{
    const auto& pots = allPots();
    for (size_t i = 0; i < pots.size(); ++i)
        if (pots[i].key == key && pots[i].channel == channel)
            return static_cast<int> (i);
    return -1;
}

juce::String potCaption (const std::string& key)
{
    static const std::map<std::string, const char*> captions {
        { "channel.aux-send", "SEND" }, { "channel.gain", "TRIM" }, { "channel.eq.high", "HIGH" },
        { "channel.eq.mid", "MID" }, { "channel.eq.low", "LOW" }, { "channel.volume", "" },
        { "master.volume", "MASTER" }, { "filter.resonance", "RES" }, { "filter.frequency", "FREQ" },
        { "master.booth", "BOOTH" }, { "master.phones-mix", "CUE/MIX" }, { "master.phones-volume", "PHONES" },
        { "master.aux-return", "FX RTN" } };
    const auto found = captions.find (key);
    return found != captions.end() ? juce::String (found->second) : juce::String();
}

bool isGuarded (const std::string& key)
{
    return key == "master.volume" || key == "master.booth" || key == "master.phones-volume";
}

bool fillsFromTheMiddle (const std::string& key)
{
    return key == "channel.eq.high" || key == "channel.eq.mid" || key == "channel.eq.low" || key == "master.phones-mix";
}

std::optional<float> restPosition (const std::string& key)
{
    // Motion's answers for the same words (a3-motion-ui MixerControls.hh: mixer-,
    // master- and filterControlRestPosition, and its channel fader's double tap):
    // one answer in the system, whichever surface the hand is on. 1.0 on gain and
    // volume is 0 dB at Core (slope_volume: full travel is 0 dB). Master, booth and
    // phones have none there -- full is the whole room, or an ear, at once.
    static const std::map<std::string, float> rests {
        { "channel.eq.high", 0.5f }, { "channel.eq.mid", 0.5f }, { "channel.eq.low", 0.5f },
        { "channel.gain", 1.f },     { "channel.aux-send", 0.f }, { "channel.volume", 1.f },
        { "master.phones-mix", 0.5f }, { "master.aux-return", 0.f }, { "filter.frequency", 0.5f },
        { "filter.resonance", 0.f } };
    const auto found = rests.find (key);
    return found != rests.end() ? std::optional<float> (found->second) : std::nullopt;
}

std::vector<std::string> keysUsed()
{
    std::vector<std::string> keys (channelPotKeys.begin(), channelPotKeys.end());
    keys.insert (keys.end(), masterPotKeys.begin(), masterPotKeys.end());
    for (const auto& [name, key] : channelKeys)
        keys.push_back (key);
    for (const auto& [key, name] : lamps)
        keys.push_back (key);
    for (const auto* key : { "filter.mode", "filter.led", "beat", "tap", "state.recall", "vu", "device.hello",
                             "channel.stem.turn", "aux-return.stem.push", "channel.stem",
                             "channel.stem.push", "channel.stem.cursor", "core.here", "aux-return.cue.led" })
        keys.emplace_back (key);
    return keys;
}
}
