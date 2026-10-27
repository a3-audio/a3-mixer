// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <optional>

#include <juce_osc/juce_osc.h>

#include "DeskControls.h"
#include "DeskOsc.h"
#include "DeskState.h"
#include "DisplayPicture.h"
#include "StartupAsk.h"

namespace desk
{
/** TAP's lamp on /beat, as long as the hardware's. */
inline constexpr double tapFlashMs = 60.0;

/** How long a "1" keeps LIVE on (Core repeats it every 5 s while it is on). */
inline constexpr double liveLeaseMs = 12000.0;

/** The lamps and the selectors as Core last told them. */
struct Indicators
{
    std::array<bool, numChannels> fx {}, cue {};
    std::optional<bool> highPass;
    std::array<int, numChannels> stemMask {}, cursor {};
    int returnCursor = display::stemMode, returnMode = display::stemMode;
    bool returnCue = false;
    /** Engine mode (Plan 4e): from Core's first `channel.source` report until a new Core. Each channel's
        source and cursor in the ring 1 2 3 4 A (Core's 1-4, 0); the decks are absent until Core reports them. */
    bool engine = false;
    std::array<int, numChannels> source {}, sourceCursor {};
    std::array<bool, display::engineDecks> deckPresent {};
    double tapLitUntilMs = -1.0;
    float bpm = 0.f;
    /** pro-DJ LIVE is a lease: on while the last "1" is younger than liveLeaseMs. */
    bool prodjLive = false;
    double prodjLiveUntilMs = -1.0;

    /** A new Core may come up as REAPER's, which reports no source: back to the interim's ring. */
    void forgetEngine()
    {
        engine = false;
        source = {};
        sourceCursor = {};
        deckPresent = {};
    }
};

/** Every message from Core on desk.osc. A damaged one changes nothing: nothing may raise into the receiver. */
class DeskInbox
{
public:
    DeskInbox (const DeskOsc& osc, DeskState& state, Indicators& indicators, StartupAsk& ask)
        : _osc (osc), _state (state), _ind (indicators), _ask (ask) {}

    void receive (const juce::OSCMessage& message, double nowMs);
    /** Lets an unrepeated LIVE run out. */
    void step (double nowMs);

private:
    const DeskOsc& _osc;
    DeskState& _state;
    Indicators& _ind;
    StartupAsk& _ask;
};
}
