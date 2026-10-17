// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskWire.h"

#include "DeskControls.h"

namespace desk
{
juce::OSCMessage DeskWire::to (const std::string& key, int number) const
{
    return juce::OSCMessage (juce::OSCAddressPattern (_osc.address (key, number)));
}

Outgoing DeskWire::pot (int pot, float value) const
{
    const auto& p = allPots()[(size_t) pot];
    auto m = to (p.key, p.channel);
    m.addFloat32 (value);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::key (const std::string& key, int channel, bool pressed) const
{
    auto m = to (key, channel);
    m.addString (pressed ? "1" : "0");
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::filterMode (bool highPass) const
{
    auto m = to ("filter.mode");
    m.addString (highPass ? "high_pass" : "low_pass");
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::channelTurn (int channel, int clicks) const
{
    auto m = to ("channel.stem.turn", channel);
    m.addInt32 (clicks);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::returnTurn (int clicks) const
{
    auto m = to ("aux-return.stem.turn");
    m.addInt32 (clicks);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::channelPush (int channel) const
{
    auto m = to ("channel.stem.push", channel);
    m.addInt32 (1);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::returnPush() const
{
    auto m = to ("aux-return.stem.push");
    m.addInt32 (1);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::tap() const
{
    // Straight to the beat clock, as the hardware's TAP: int 1, the analyzer reads i or f.
    auto m = to ("tap");
    m.addInt32 (1);
    return { Outgoing::To::beatClock, m };
}

Outgoing DeskWire::hello (const juce::String& truthDigest, const juce::String& device) const
{
    auto m = to ("device.hello");
    m.addString (device);
    m.addString (truthDigest);
    return { Outgoing::To::core, m };
}

Outgoing DeskWire::recall() const
{
    auto m = to ("state.recall");
    m.addInt32 (1);
    return { Outgoing::To::core, m };
}
}
