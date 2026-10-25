// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <functional>
#include <memory>
#include <vector>

#include <juce_gui_basics/juce_gui_basics.h>

#include "DeskControlsUi.h"
#include "DeskIndicatorsUi.h"
#include "DeskInbox.h"
#include "DeskLayout.h"
#include "DeskLink.h"
#include "DeskLook.h"
#include "DeskMeters.h"
#include "DeskState.h"
#include "DeskWire.h"
#include "StartupAsk.h"
#include "VuInbox.h"
#include "shared/TruthKeeperLink.h"

namespace desk
{
/** The desk's one clock: announced, receive and step compare its readings,
    so every caller takes them from here. */
inline double nowMs() { return juce::Time::getMillisecondCounterHiRes(); }

/** A fingertip on the primary display, in pixels: the one place the desk asks the screen. */
float currentFingertip();

/** The whole desk on screen (spec §4): every control in the hardware's
    place, values from Core, hands only once Core has answered. The sending
    is handed in (DeskLink in the app, a recorder in the tests). Everything
    here runs on the message thread. */
class DeskComponent : public juce::Component, private juce::Timer
{
public:
    using Send = std::function<bool (const Outgoing&)>;

    explicit DeskComponent (Send send, juce::String device = "desk");
    ~DeskComponent() override;

    /** A truth lacking a key the desk needs builds nothing: no wire, no sending, the status says what is missing. */
    void useTruth (a3::OscTruth truth);
    void setLinkState (DeskLink::Opened opened);
    void announced (const a3::Announcement& announcement, double nowMs);
    void receive (const juce::OSCMessage& message, double nowMs);
    /** The 25 Hz work: asking Core, meters, displays, lamps, hands. */
    void step (double nowMs);

    void touchPot (int pot, float value);
    void setLocked (bool locked);
    /** While true no hand is taken and every control dims, as before Core answers. */
    void setHandsWithheld (bool withheld);
    bool handsAccepted() const;
    const DeskMeters* meters() const { return _meters.get(); }
    /** The control a truth key stands for, for every control the desk has a key for: pots and fader
        ("channel.volume", "master.booth"), "channel.cue", "channel.filter", "tap" (0 = the first), the INPUT
        encoders ("channel.stem.turn"/".push"), SELECT ("aux-return.stem.turn"/".push", channel 0), and
        "filter.mode" (1 = HPF, 2 = LPF). Channel 0 for the master section; nullptr for anything else. */
    juce::Component* controlFor (const std::string& key, int channel) const;

    const DeskOsc* osc() const { return _osc.get(); }
    VuInbox* vuInbox() { return _vu.get(); }
    const DeskState& state() const { return _state; }
    juce::String statusText() const { return _statusText; }

    void paint (juce::Graphics&) override;
    void resized() override;
    bool keyPressed (const juce::KeyPress&) override;
    bool keyStateChanged (bool isKeyDown) override;

private:
    static constexpr int stepsPerSecond = 25;

    void timerCallback() override { step (nowMs()); }
    void buildControls();
    void buildStrip (int channel);
    void buildMaster();
    void send (const Outgoing& out);
    void syncControls();
    void showLamps();
    void showMeters();
    void showDisplays (double dtSeconds);
    void updateHands();
    void releaseLostGrabs (bool hands);
    void show (juce::Component& control, bool takesHands = true);
    void showStatus();
    bool liveOffered() const;
    void liveTapped();
    juce::String statusRight() const;
    void pressKey (const std::string& key, int channel, bool down);
    void pressFilter (bool highPass, bool down);
    void tap();

    Send _send;
    juce::String _device;
    DeskLook _look;
    DeskLayout _layout;
    std::unique_ptr<DeskOsc> _osc;
    std::unique_ptr<DeskWire> _wire;
    std::unique_ptr<VuInbox> _vu;
    std::unique_ptr<DeskMeters> _meters;
    std::unique_ptr<DeskInbox> _inbox;
    DeskState _state { static_cast<int> (allPots().size()) };
    Indicators _ind;
    StartupAsk _ask;
    CoreWatch _core;
    DeskLink::Opened _link = DeskLink::Opened::noTruth;
    juce::String _truthProblem, _statusText;
    bool _locked = false, _withheld = false, _handsShown = false;
    double _now = 0.0, _lastStep = 0.0;

    std::vector<juce::Component*> _handed;   // every control and indicator but the pots: enabled with the hands
    std::vector<int> _keysHeld;               // key codes down: autorepeat acts once
    std::vector<juce::Slider*> _potControl;   // by pot index: a DeskKnob, or a DeskFader for channel.volume
    std::vector<std::unique_ptr<DeskKnob>> _knobs;
    std::array<std::unique_ptr<DeskFader>, numChannels> _faders;
    std::array<std::unique_ptr<DeskEncoder>, numChannels> _encoders;
    std::unique_ptr<DeskEncoder> _select;
    std::array<std::unique_ptr<DeskKey>, numChannels> _taps, _fxKeys, _cueKeys;
    std::unique_ptr<DeskKey> _hpf, _lpf, _lock;
    std::array<std::unique_ptr<LedColumn>, numChannels> _leds;
    std::unique_ptr<OutputMatrix> _matrix;
    std::array<std::unique_ptr<OledView>, numChannels> _displays;
    std::unique_ptr<OledView> _returnDisplay;
    std::unique_ptr<StatusLine> _status;
    std::array<std::array<display::ClipHold, display::channelMeters>, numChannels> _channelClips;
    std::array<display::ClipHold, 2> _returnClips;
};
}
