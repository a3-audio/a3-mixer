// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

/*

  A3 Motion UI
  Copyright (C) 2026 Raphael Eismann

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.

*/

#pragma once

#include <string>
#include <utility>

// The desk takes its truth from Core (spec truth-from-core, step 3), like
// Motion and StemDeck: it starts on the truth Core last served, hears
// /core/here, and on a fingerprint it does not have fetches, verifies, stores
// and restarts. The decisions are here, pure -- the same as StemDeck's
// keeper, with the same tests; the JUCE side is TruthKeeperLink.
//
// The port and the word below are all a device knows before it has a truth;
// a3-core's guard allows exactly these, by name.
namespace a3::truthkeeper
{
constexpr int announcePort = 7790;
inline const char *announceAddress = "/core/here";

inline std::string
cachePath (std::string const &home)
{
  return home + "/.cache/a3/a3-osc.json";
}

/** With $A3_OSC_TRUTH set, that file wins at every start: following Core
 *  would restart the desk into the same file forever. */
inline bool
followsCore (char const *override)
{
  return override == nullptr || *override == '\0';
}

/** url and fingerprint, plus Core's boot id since it sends one (an older
 *  Core sends two). The desk only follows the fingerprint, so it ignores the
 *  boot id. */
inline bool
announcementSize (int arguments)
{
  return arguments == 2 || arguments == 3;
}

/** Never fetch, never restart for the truth the desk already has. */
inline bool
needsFetch (std::string const &announced, std::string const &own)
{
  return announced != own;
}

/** Whether an announcement is fetched: never under an override (the desk
 *  still hears /core/here, for "Core silent"), else only another truth. */
inline bool
shouldFetch (bool followingCore, std::string const &announced,
             std::string const &own)
{
  return followingCore && needsFetch (announced, own);
}

inline bool
verified (std::string const &bodyHash, std::string const &header,
          std::string const &announced)
{
  return !bodyHash.empty () && bodyHash == header && header == announced;
}

/** $A3_OSC_TRUTH, else the cache if it reads as a truth, else the package's. */
inline std::string
startPath (char const *override, std::string const &cache, bool cacheUsable,
           std::string const &package)
{
  if (!followsCore (override))
    return override;
  return cacheUsable ? cache : package;
}

/** How long the desk waits for Core's announcement before it opens on the
 *  truth on disk (decided 2026-10-07, a3-system#74). */
constexpr int startupWaitMs = 10000;

enum class StartupStep
{
  stay,
  open,
  fetch
};

/** The desk's start-up: the window opens once -- on Core's truth when Core
 *  announces within startupWaitMs (fetched first if it differs), else on what
 *  is on disk. A fetch that fails still opens: on what is there. Pure;
 *  TruthKeeperLink drives it on the message thread. */
class StartupWait
{
public:
  explicit StartupWait (std::string candidate)
      : _candidate (std::move (candidate))
  {
  }

  StartupStep
  announced (std::string const &fingerprint)
  {
    if (_open || _fetching)
      return StartupStep::stay;
    if (!needsFetch (fingerprint, _candidate))
      return openNow ();
    _fetching = true;
    return StartupStep::fetch;
  }

  StartupStep
  fetched ()
  {
    _fetching = false;
    return _open ? StartupStep::stay : openNow ();
  }

  StartupStep
  timedOut ()
  {
    return _open ? StartupStep::stay : openNow ();
  }

  bool
  isOpen () const
  {
    return _open;
  }

private:
  StartupStep
  openNow ()
  {
    _open = true;
    return StartupStep::open;
  }

  std::string _candidate;
  bool _open = false;
  bool _fetching = false;
};
}
