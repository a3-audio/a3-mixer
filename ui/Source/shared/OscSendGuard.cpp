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

#include "OscSendGuard.h"

#include <atomic>
#include <stdexcept>

namespace a3
{

namespace
{
std::atomic<bool> refused{ false };
}

namespace
{
void
refuseIfTesting (juce::String const &host, int port)
{
  if (oscSendersRefused ())
    throw std::logic_error (
        ("refused to aim an OSC sender at " + host + ":" + juce::String (port)
         + " -- tests send nothing (a3-motion-ui #67)")
            .toStdString ());
}
}

void
refuseOscSenders ()
{
  refused.store (true);
}

bool
oscSendersRefused ()
{
  return refused.load ();
}

bool
connectOscSender (juce::OSCSender &sender, juce::String const &host, int port)
{
  refuseIfTesting (host, port);
  return sender.connect (host, port);
}

bool
connectOscSenderToSocket (juce::OSCSender &sender, juce::DatagramSocket &socket,
                          juce::String const &host, int port)
{
  refuseIfTesting (host, port);
  return sender.connectToSocket (socket, host, port);
}

}
