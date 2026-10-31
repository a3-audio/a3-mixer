// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskInbox.h"

#include <cmath>

#include "DeskDelay.h"

namespace desk
{
namespace
{
std::optional<float> numberIn (const juce::OSCArgument& a)
{
    // Network input: NaN/inf never reaches the state.
    if (a.isFloat32())
        return std::isfinite (a.getFloat32()) ? std::optional<float> (a.getFloat32()) : std::nullopt;
    if (a.isInt32())
        return static_cast<float> (a.getInt32());
    return std::nullopt;
}

std::optional<int> countIn (const juce::OSCArgument& a, int upper)
{
    if (! a.isInt32() || a.getInt32() < 0 || a.getInt32() > upper)
        return std::nullopt;
    return a.getInt32();
}
}

void DeskInbox::step (double nowMs)
{
    if (_ind.prodjLive && nowMs >= _ind.prodjLiveUntilMs)
        _ind.prodjLive = false;
}

void DeskInbox::receive (const juce::OSCMessage& m, double nowMs)
{
    _ask.answered();   // anything on desk.osc: Core follows this desk
    const auto found = _osc.match (m.getAddressPattern().toString());
    if (! found || m.isEmpty())
        return;
    const auto& key = found->key;
    const auto ch = found->number;
    const auto slot = (size_t) juce::jmax (0, ch - 1);

    if (const auto pot = potIndex (key, ch); pot >= 0)
    {
        if (const auto v = numberIn (m[0]))
            _state.setFromPeer (pot, *v);
        return;
    }
    if (key == "channel.filter.led" || key == "channel.cue.led")
    {
        if (const auto v = numberIn (m[0]))
            (key == "channel.cue.led" ? _ind.cue : _ind.fx)[slot] = *v > 0.5f;
        return;
    }
    if (key == "filter.led")
    {
        if (m[0].isString() && (m[0].getString() == "high_pass" || m[0].getString() == "low_pass"))
            _ind.highPass = m[0].getString() == "high_pass";
        return;
    }
    if (key == "channel.stem")
    {
        if (const auto v = countIn (m[0], (1 << display::pairs) - 1))
            _ind.stemMask[slot] = *v;
        return;
    }
    if (key == "channel.stem.cursor")
    {
        if (const auto v = countIn (m[0], display::analogInput))
            _ind.cursor[slot] = *v;
        return;
    }
    if (key == "channel.source" || key == "channel.source.cursor")
    {
        if (const auto v = countIn (m[0], display::coreDecks))
        {
            (key == "channel.source" ? _ind.source : _ind.sourceCursor)[slot] = *v;
            _ind.engine = _ind.engine || key == "channel.source";
        }
        return;
    }
    if (key == "stemdeck.present")
    {
        // Core numbers decks 1-4, the ring offers all four.
        if (const auto v = countIn (m[0], 1); v && slot < _ind.deckPresent.size())
            _ind.deckPresent[slot] = *v == 1;
        return;
    }
    if (const auto row = delay::rowOfValueKey (key))
    {
        if (const auto v = numberIn (m[0]))
            _ind.delayValues[(size_t) *row] = *v;
        return;
    }
    if (key == "aux-return.cue.led")
    {
        if (const auto v = numberIn (m[0]))
            _ind.returnCue = *v > 0.5f;
        return;
    }
    if (key == "prodj.live")
    {
        // Exactly one int 0 or 1; anything else neither lights nor ends it.
        if (m.size() != 1)
            return;
        if (const auto v = countIn (m[0], 1))
        {
            _ind.prodjLive = *v == 1;
            _ind.prodjLiveUntilMs = nowMs + liveLeaseMs;
        }
        return;
    }
    if (key == "beat")
    {
        _ind.tapLitUntilMs = nowMs + tapFlashMs;
        if (m.size() >= 3)
            if (const auto tempo = numberIn (m[2]))
                _ind.bpm = *tempo;
    }
}
}
