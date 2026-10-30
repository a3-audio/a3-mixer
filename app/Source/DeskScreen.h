// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <functional>
#include <string>
#include <vector>

#include <juce_core/juce_core.h>

/** The desk on the rig's screen, an i3 workspace among A3 Motion's and StemDeck's: full screen however it is
    started, and the workspaces as StemDeck's and A3 Motion's switch offers them (StemDeck's Workspaces.h,
    A3 Motion's io/Workspaces.hh). */
namespace desk::screen
{
/** Runs a command line and returns what it printed, "" when it could not run. The tests hand in a fake,
    so no i3-msg runs in them. */
using I3Runner = std::function<std::string (const std::vector<std::string>& argv)>;

/** Full screen unless --windowed: the desk is full screen whichever way it is started. */
bool wantsFullScreen (const juce::StringArray& commandLine);
/** i3's own full screen for X window `window`: JUCE's setFullScreen is a maximise, which i3 tiles under its bar. */
std::vector<std::string> fullScreenCommand (unsigned long window);

struct Workspace
{
    int number = 0;
    std::string label;   // "3:REAPER" -> "REAPER"
    bool current = false;
};

/** What `i3-msg -t get_workspaces` printed: the workspaces with a number to go to; anything else is none. */
std::vector<Workspace> parseWorkspaces (const std::string& i3Reply);
std::vector<std::string> listCommand();
std::vector<std::string> goToCommand (int number);

/** StemDeck's workspace: where the switch's app key goes. */
inline constexpr int stemDeckWorkspace = 2;

/** Where the switch sits, StemDeck's and A3 Motion's numbers (shares of the window's width; at the rig's
    768 px their first sizes): the app key, then the arrow, at the window's right edge. */
struct SwitcherGeometry
{
    int margin = 0, arrowWidth = 0, gap = 0, appKeyWidth = 0, listTop = 0, listWidth = 0, listKeyHeight = 0,
        listGap = 0;
};
SwitcherGeometry switcherGeometry (int windowWidth);

/** Spawns the command (posix_spawnp, never fork: StemDeck's SpawnOutput) and returns its output; killed
    after a second. */
I3Runner systemI3Runner();
}
