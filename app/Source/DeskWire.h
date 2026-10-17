// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <string>

#include <juce_osc/juce_osc.h>

#include "DeskOsc.h"

namespace desk
{
struct Outgoing
{
    enum class To { core, beatClock };
    To to;
    juce::OSCMessage message;
};

/** Every message the desk sends, built from truth keys. Keys, turns and tap as the
    hardware sends them (D5); pots as float32 (plan change #3), not the hardware's
    strings -- do not change them back. */
class DeskWire
{
public:
    explicit DeskWire (const DeskOsc& osc) : _osc (osc) {}

    Outgoing pot (int pot, float value) const;
    /** FX and CUE as the panel sends them: "1" on press, "0" on release; what a press means is Core's. */
    Outgoing key (const std::string& key, int channel, bool pressed) const;
    /** HPF or LPF, on press only: the word, as a3-mixer.py sends it. */
    Outgoing filterMode (bool highPass) const;
    Outgoing channelTurn (int channel, int clicks) const;
    Outgoing returnTurn (int clicks) const;
    Outgoing channelPush (int channel) const;
    Outgoing returnPush() const;
    Outgoing tap() const;
    Outgoing hello (const juce::String& truthDigest, const juce::String& device = "desk") const;
    Outgoing recall() const;

private:
    juce::OSCMessage to (const std::string& key, int number = 0) const;

    const DeskOsc& _osc;
};
}
