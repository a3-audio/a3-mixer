// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "TruthKeeperLink.h"

#include <iostream>
#include <utility>

#include <juce_cryptography/juce_cryptography.h>

namespace a3
{
std::optional<Announcement> readAnnouncement (const juce::OSCMessage& message)
{
    if (message.getAddressPattern().toString() != truthkeeper::announceAddress
        || ! truthkeeper::announcementSize (message.size()))
        return std::nullopt;
    for (const auto& argument : message)
        if (! argument.isString())
            return std::nullopt;
    return Announcement { message[0].getString(), message[1].getString(),
                          message.size() == 3 ? message[2].getString() : juce::String() };
}

TruthKeeperLink::TruthKeeperLink (juce::File cache, std::function<juce::String (const juce::String&)> usable,
                                  std::function<void()> onNewTruth, bool followingCore)
    : _followingCore (followingCore), _cache (std::move (cache)), _usable (std::move (usable)),
      _onNewTruth (std::move (onNewTruth))
{
}

TruthKeeperLink::~TruthKeeperLink()
{
    _receiver.removeListener (this);
    _receiver.disconnect();
    _fetcher.removeAllJobs (true, 6000);
}

bool TruthKeeperLink::start()
{
    // Shared with Motion and StemDeck on this machine: all reuse the port, all hear it.
    _socket.setEnablePortReuse (true);
    if (! _socket.bindToPort (truthkeeper::announcePort) || ! _receiver.connectToSocket (_socket))
    {
        std::cerr << "A3 Desk: cannot listen for Core's truth on " << truthkeeper::announcePort << std::endl;
        return false;
    }
    _receiver.addListener (this);
    return true;
}

void TruthKeeperLink::follow (std::string own)
{
    _own = std::move (own);
}

void TruthKeeperLink::oscMessageReceived (const juce::OSCMessage& message)
{
    const auto announcement = readAnnouncement (message);
    if (! announcement)
        return;
    if (onHeard)
        onHeard (*announcement);
    if (truthkeeper::shouldFetch (_followingCore, announcement->fingerprint.toStdString(), _own))
        fetch (announcement->url, announcement->fingerprint);
}

void TruthKeeperLink::finished (bool written)
{
    if (! written)
        return;
    std::cerr << "A3 Desk: Core announced another truth, reloading on it" << std::endl;
    _onNewTruth();
}

// fetch(), take(), refuse(): copied from a3-motion-ui's TruthKeeperLink.cc, "A3 Motion" -> "A3 Desk".
void
TruthKeeperLink::fetch (juce::String const &url, juce::String const &announced)
{
  if (_busy.exchange (true))
    return;
  _fetcher.addJob ([this, url, announced] {
    auto const written = take (url, announced);
    _busy = false;
    juce::MessageManager::callAsync (
        [link = juce::WeakReference<TruthKeeperLink> (this), written] {
          if (auto *alive = link.get ())
            alive->finished (written);
        });
  });
}

bool
TruthKeeperLink::take (juce::String url, juce::String announced)
{
  juce::StringPairArray headers;
  int status = 0;
  auto stream = juce::URL (url).createInputStream (
      juce::URL::InputStreamOptions (juce::URL::ParameterHandling::inAddress)
          .withConnectionTimeoutMs (5000)
          .withResponseHeaders (&headers)
          .withStatusCode (&status));
  if (stream == nullptr || status != 200)
    {
      refuse ("fetch failed (status " + juce::String (status) + ")");
      return false;
    }
  juce::MemoryBlock body;
  stream->readIntoMemoryBlock (body);
  auto const hash = juce::SHA256 (body).toHexString ();
  if (!truthkeeper::verified (hash.toStdString (),
                              headers["X-A3-Truth"].toStdString (),
                              announced.toStdString ()))
    {
      refuse ("body, header and announcement do not agree");
      return false;
    }
  if (auto const why = _usable (body.toString ()); why.isNotEmpty ())
    {
      refuse (why);
      return false;
    }
  _cache.getParentDirectory ().createDirectory ();
  juce::TemporaryFile temporary (_cache);
  if (!temporary.getFile ().replaceWithData (body.getData (), body.getSize ())
      || !temporary.overwriteTargetFileWithTemporary ())
    {
      refuse ("cannot write " + _cache.getFullPathName ());
      return false;
    }
  return true;
}

void
TruthKeeperLink::refuse (juce::String const &reason)
{
  // Said once per reason, not every 2 s while Core keeps announcing it.
  if (reason == _lastReason)
    return;
  _lastReason = reason;
  std::cerr << "A3 Desk: Core's truth refused: " << reason << std::endl;
}
}
