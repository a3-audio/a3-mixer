// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <optional>
#include <vector>

#include <juce_core/juce_core.h>

namespace desk
{
/** How the desk asks Core for the room (spec §4.4): hello at start and every
    30 s, /state/recall at start whatever has arrived, then every 5 s until
    anything comes back, for two minutes.
    Never a value: the desk does not dump positions (the hardware's
    DeskInFront would overwrite the room with a screen's idea of it). The
    desk takes no hand until Core has answered once. Pure; the caller passes
    the clock and sends. */
class StartupAsk
{
public:
    static constexpr double helloEveryMs = 30000.0, recallEveryMs = 5000.0, giveUpAfterMs = 120000.0;
    enum class Send { hello, recall };

    /** What is due now. Nothing while the desk does not speak Core's truth: a
        stale hello closes the host in Core's gate (Motion's beside it too), and
        a stale desk asking for recall would flood Core with replays. */
    std::vector<Send> due (double nowMs, bool speaksCoresTruth);
    void answered() { _joined = true; }
    /** A new Core (another boot id): ask again from the start. */
    void coreRestarted (double nowMs);
    bool joined() const { return _joined; }
    bool gaveUp (double nowMs) const;

private:
    std::optional<double> _lastHello, _lastRecall, _askingSince;
    bool _joined = false;
};

/** Core's announcements (/core/here every 2 s): whether Core is there, which
    truth it serves, and whether it is a new Core. */
class CoreWatch
{
public:
    static constexpr double silentAfterMs = 5000.0;

    /** True when the desk must ask again: a new Core (a boot id other than
        the last one heard; an older Core sends none, and is never "new"), or
        a Core heard again after silence -- what it sent meanwhile is lost,
        and after a minute it no longer follows the desk. */
    bool heard (const juce::String& fingerprint, const juce::String& bootId, double nowMs);
    bool silent (double nowMs) const;
    const juce::String& fingerprint() const { return _fingerprint; }

private:
    std::optional<double> _lastMs;
    juce::String _bootId, _fingerprint;
};
}
