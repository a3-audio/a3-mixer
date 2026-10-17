// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskLink.h"

#include "shared/OscSendGuard.h"

namespace desk
{
bool bindExclusively (juce::DatagramSocket& socket, int port)
{
    return socket.setEnablePortReuse (false) && socket.bindToPort (port);
}

DeskLink::DeskLink (const DeskOsc& osc, VuInbox& vu, std::function<void (const juce::OSCMessage&)> onMessage)
    : _osc (osc), _onMessage (std::move (onMessage)), _meters (osc, vu)
{
}

DeskLink::~DeskLink()
{
    // Disconnect first: it stops the receiver threads. JUCE's realtime listeners are a
    // LightweightListenerList, whose remove() races with the meter thread iterating it.
    _receiver.disconnect();
    _vuReceiver.disconnect();
    _receiver.removeListener (this);
    _vuReceiver.removeListener (&_meters);
}

DeskLink::Opened DeskLink::open()
{
    if (! bindExclusively (_socket, _osc.ownPort()))
        return Opened::portTaken;
    if (! bindExclusively (_vuSocket, _osc.vuPort()))
        return Opened::vuPortTaken;
    // MessageLoopCallback: desk.osc reaches DeskInbox on the message thread only.
    _receiver.addListener (this);
    _receiver.connectToSocket (_socket);
    _vuReceiver.addListener (&_meters);
    _vuReceiver.connectToSocket (_vuSocket);
    const auto core = _osc.core();
    const auto clock = _osc.beatClock();
    _open = a3::connectOscSenderToSocket (_toCore, _socket, core.host, core.port)
            && a3::connectOscSender (_toBeatClock, clock.host, clock.port);
    return _open ? Opened::ok : Opened::noSender;
}

bool DeskLink::send (const Outgoing& out)
{
    if (! _open)
        return false;
    return out.to == Outgoing::To::core ? _toCore.send (out.message) : _toBeatClock.send (out.message);
}

void DeskLink::Meters::oscMessageReceived (const juce::OSCMessage& m)
{
    if (m.isEmpty() || ! m[0].isFloat32())
        return;
    if (const auto n = osc.vuNumberOf (m.getAddressPattern().toString()))
        vu.note (*n, m[0].getFloat32());
}

void DeskLink::Meters::oscBundleReceived (const juce::OSCBundle& bundle)
{
    for (const auto& element : bundle)
    {
        if (element.isMessage())
            oscMessageReceived (element.getMessage());
        else if (element.isBundle())
            oscBundleReceived (element.getBundle());
    }
}

juce::String statusFor (DeskLink::Opened opened)
{
    switch (opened)
    {
        case DeskLink::Opened::ok: return {};
        case DeskLink::Opened::portTaken: return "another desk runs on this machine";
        case DeskLink::Opened::vuPortTaken: return "another program holds the desk's meter port";
        case DeskLink::Opened::noSender: return "the desk cannot send to Core or the beat clock";
        case DeskLink::Opened::noTruth: return "waiting for Core's truth";
    }
    return {};
}
}
