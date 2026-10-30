// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "StartupAsk.h"

namespace desk
{
std::vector<StartupAsk::Send> StartupAsk::due (double nowMs, bool speaksCoresTruth)
{
    std::vector<Send> out;
    if (! speaksCoresTruth)
        return out;
    if (! _lastHello || nowMs - *_lastHello >= helloEveryMs)
    {
        out.push_back (Send::hello);
        _lastHello = nowMs;
    }
    // The first ask always recalls: a Core that still follows this host (the desk restarted within a minute)
    // replays nothing on its hello but keeps relaying to it, and that relay is no state (a3nuc2, 2026-10-30).
    if (! _askingSince)
    {
        _askingSince = nowMs;
        out.push_back (Send::recall);
        _lastRecall = nowMs;
        return out;
    }
    if (_joined)
        return out;
    if (nowMs - *_askingSince <= giveUpAfterMs && (! _lastRecall || nowMs - *_lastRecall >= recallEveryMs))
    {
        out.push_back (Send::recall);
        _lastRecall = nowMs;
    }
    return out;
}

void StartupAsk::coreRestarted (double nowMs)
{
    _joined = false;
    _lastHello.reset();
    _lastRecall.reset();
    _askingSince.reset();   // the clock starts at the first call that may ask
}

bool StartupAsk::gaveUp (double nowMs) const
{
    return ! _joined && _askingSince && nowMs - *_askingSince > giveUpAfterMs;
}

bool CoreWatch::heard (const juce::String& fingerprint, const juce::String& bootId, double nowMs)
{
    const bool newCore = _lastMs.has_value() && bootId.isNotEmpty() && _bootId.isNotEmpty() && bootId != _bootId;
    const bool backFromSilence = _lastMs.has_value() && silent (nowMs);
    _lastMs = nowMs;
    _fingerprint = fingerprint;
    if (bootId.isNotEmpty())
        _bootId = bootId;
    return newCore || backFromSilence;
}

bool CoreWatch::silent (double nowMs) const
{
    return ! _lastMs || nowMs - *_lastMs > silentAfterMs;
}
}
