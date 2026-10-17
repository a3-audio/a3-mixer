// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <functional>

#include <juce_osc/juce_osc.h>

#include "DeskOsc.h"
#include "DeskWire.h"
#include "VuInbox.h"

namespace desk
{
/** Bind `socket` to `port` and to nothing else: JUCE makes every DatagramSocket
    reusable (SO_REUSEADDR in its constructor), and on Linux a second UDP socket
    then binds the same port without a word -- a second desk on one machine
    would run half-deaf. Reuse is switched off before binding, so the second bind fails. */
bool bindExclusively (juce::DatagramSocket& socket, int port);

/** The desk's sockets. desk.osc is received *and* sent from, so Core can tell
    this desk from a Motion on the same machine by the source port
    (a3-core a3_core_desks). desk.osc's messages reach `onMessage` on the
    message thread (DeskInbox and DeskState are not locked); desk.vu feeds the
    VuInbox on the receiver's own thread (the one structure that is). */
class DeskLink : private juce::OSCReceiver::Listener<juce::OSCReceiver::MessageLoopCallback>
{
public:
    enum class Opened { ok, portTaken, vuPortTaken, noTruth };

    DeskLink (const DeskOsc& osc, VuInbox& vu, std::function<void (const juce::OSCMessage&)> onMessage);
    ~DeskLink() override;

    Opened open();
    bool send (const Outgoing& out);

private:
    struct Meters : juce::OSCReceiver::Listener<juce::OSCReceiver::RealtimeCallback>
    {
        Meters (const DeskOsc& o, VuInbox& v) : osc (o), vu (v) {}
        void oscMessageReceived (const juce::OSCMessage& m) override;
        void oscBundleReceived (const juce::OSCBundle& b) override;
        const DeskOsc& osc;
        VuInbox& vu;
    };

    void oscMessageReceived (const juce::OSCMessage& message) override { _onMessage (message); }

    const DeskOsc& _osc;
    std::function<void (const juce::OSCMessage&)> _onMessage;
    Meters _meters;
    juce::DatagramSocket _socket { false }, _vuSocket { false };
    juce::OSCReceiver _receiver, _vuReceiver;
    juce::OSCSender _toCore, _toBeatClock;
    bool _open = false;
};

juce::String statusFor (DeskLink::Opened opened);
}
