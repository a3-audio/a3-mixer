// SPDX-FileCopyrightText: 2026 Patric Schmitz
//
// SPDX-License-Identifier: GPL-3.0-or-later

/*

  A3 Motion UI
  Copyright (C) 2026 Patric Schmitz

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

#include <juce_osc/juce_osc.h>

namespace a3
{

/** The one way the desk aims an OSC sender.
 *
 *  The test runner calls refuseOscSenders() before any test runs. From then
 *  on connectOscSender() throws std::logic_error, whatever the host -- so a
 *  test that builds an engine without a backend, or a sender from the truth,
 *  fails instead of sending positions and pot values to the Core the truth
 *  names, the live one on the rig (#67). Every host, not only real ones: the
 *  same test then fails on every machine and with every truth, rather than
 *  only where the truth happens to name a reachable Core. There is no way
 *  back. The app never calls it, so there this only connects. */
bool connectOscSender (juce::OSCSender &sender, juce::String const &host,
                       int port);

/** The same, for a sender that shares the desk's own socket. */
bool connectOscSenderToSocket (juce::OSCSender &sender,
                               juce::DatagramSocket &socket,
                               juce::String const &host, int port);

void refuseOscSenders ();
bool oscSendersRefused ();

}
