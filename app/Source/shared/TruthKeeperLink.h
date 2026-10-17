// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <atomic>
#include <functional>
#include <optional>
#include <string>

#include <juce_osc/juce_osc.h>

#include "TruthKeeper.h"

namespace a3
{
struct Announcement
{
    juce::String url, fingerprint, bootId;
};

/** /core/here's url, fingerprint and -- from a Core that sends one -- boot id. */
std::optional<Announcement> readAnnouncement (const juce::OSCMessage& message);

/** Hears /core/here (port shared with Motion and StemDeck on one machine:
    reuse on), tells `onHeard` of every announcement, and fetches a truth the
    desk does not have off the message thread; once it is written whole into
    the cache, `onNewTruth` reloads the desk in-process (vendored from
    a3-motion-ui's TruthKeeperLink without its start-up wait: the desk opens
    at once and dims until Core answers). */
class TruthKeeperLink : private juce::OSCReceiver::Listener<juce::OSCReceiver::MessageLoopCallback>
{
public:
    TruthKeeperLink (juce::File cache, std::function<juce::String (const juce::String& body)> usable,
                     std::function<void()> onNewTruth);
    ~TruthKeeperLink() override;

    bool start();
    void follow (std::string own);

    std::function<void (const Announcement&)> onHeard;

private:
    void oscMessageReceived (const juce::OSCMessage& message) override;
    void fetch (const juce::String& url, const juce::String& announced);
    bool take (juce::String url, juce::String announced);
    void finished (bool written);
    void refuse (const juce::String& reason);

    std::string _own;
    juce::File _cache;
    std::function<juce::String (const juce::String&)> _usable;
    std::function<void()> _onNewTruth;
    juce::DatagramSocket _socket { true };
    juce::OSCReceiver _receiver;
    std::atomic<bool> _busy { false };
    juce::String _lastReason;
    JUCE_DECLARE_WEAK_REFERENCEABLE (TruthKeeperLink)
    // Last: destroyed first, so a job it still waits for finds the rest alive.
    juce::ThreadPool _fetcher { juce::ThreadPoolOptions {}.withNumberOfThreads (1) };
};
}
