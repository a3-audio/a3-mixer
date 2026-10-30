// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskScreen.h"

#include <thread>

#include <spawn.h>
#include <sys/wait.h>

extern char** environ;

namespace desk::screen
{
bool wantsFullScreen (const juce::StringArray& commandLine) { return commandLine.contains ("--fullscreen"); }

std::vector<std::string> nextWorkspaceCommand() { return { "i3-msg", "-q", "workspace next" }; }

I3Runner systemI3Runner()
{
    return [] (const std::vector<std::string>& argv) {
        if (argv.empty())
            return;
        std::vector<char*> args;
        for (const auto& word : argv)
            args.push_back (const_cast<char*> (word.c_str()));
        args.push_back (nullptr);
        // posix_spawn shares the caller's memory until exec: nothing is copied (StemDeck's SpawnOutput).
        pid_t pid = -1;
        if (posix_spawnp (&pid, args[0], nullptr, nullptr, args.data(), environ) != 0)
            return;
        // Reaped off the message thread: i3-msg -q answers at once, but a hung one must not freeze the desk.
        std::thread ([pid] {
            int status = 0;
            waitpid (pid, &status, 0);
        }).detach();
    };
}
}
