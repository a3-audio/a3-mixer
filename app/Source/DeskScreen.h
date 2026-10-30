// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <functional>
#include <string>
#include <vector>

#include <juce_core/juce_core.h>

/** The desk on the rig's screen: full screen when launched so (as StemDeck's --fullscreen), and a key to
    the next i3 workspace, since full screen hides i3's bar (a3-core's i3 config, 2026-10-30). */
namespace desk::screen
{
/** Runs a command line; the tests hand in a fake, so no i3-msg runs in them. */
using I3Runner = std::function<void (const std::vector<std::string>& argv)>;

bool wantsFullScreen (const juce::StringArray& commandLine);
std::vector<std::string> nextWorkspaceCommand();
/** Spawns the command (posix_spawnp, never fork) and does not wait for it on the caller's thread. */
I3Runner systemI3Runner();
}
