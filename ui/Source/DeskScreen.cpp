// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskScreen.h"

#include <cctype>
#include <chrono>
#include <cmath>
#include <csignal>

#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

namespace desk::screen
{
namespace
{
using Clock = std::chrono::steady_clock;
constexpr int i3TimeoutMs = 1000;

std::size_t digitsEnd (const std::string& name)
{
    std::size_t end = 0;
    while (end < name.size() && std::isdigit ((unsigned char) name[end]))
        ++end;
    return end;
}

pid_t spawnWithStdoutTo (const std::vector<std::string>& argv, int writeEnd)
{
    std::vector<char*> args;
    for (const auto& word : argv)
        args.push_back (const_cast<char*> (word.c_str()));
    args.push_back (nullptr);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init (&actions);
    posix_spawn_file_actions_adddup2 (&actions, writeEnd, STDOUT_FILENO);
    posix_spawn_file_actions_addopen (&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    pid_t pid = -1;
    const auto failed = posix_spawnp (&pid, args[0], &actions, nullptr, args.data(), environ) != 0;
    posix_spawn_file_actions_destroy (&actions);
    return failed ? -1 : pid;
}

bool readUntilClosed (int readEnd, Clock::time_point deadline, std::string& output)
{
    char chunk[4096];
    for (;;)
    {
        const auto left = std::chrono::duration_cast<std::chrono::milliseconds> (deadline - Clock::now()).count();
        if (left <= 0)
            return false;
        pollfd fd { readEnd, POLLIN, 0 };
        if (poll (&fd, 1, (int) left) <= 0)
            continue;
        const auto got = read (readEnd, chunk, sizeof (chunk));
        if (got == 0)
            return true;
        if (got > 0)
            output.append (chunk, (size_t) got);
    }
}

/** StemDeck's spawnForOutput (Source/SpawnOutput.cpp). */
std::string spawnForOutput (const std::vector<std::string>& argv, int timeoutMs)
{
    if (argv.empty())
        return {};
    int ends[2];
    if (pipe2 (ends, O_CLOEXEC) != 0)
        return {};
    const auto pid = spawnWithStdoutTo (argv, ends[1]);
    close (ends[1]);
    if (pid < 0)
    {
        close (ends[0]);
        return {};
    }
    std::string output;
    const auto finished = readUntilClosed (ends[0], Clock::now() + std::chrono::milliseconds (timeoutMs), output);
    close (ends[0]);
    if (! finished)
        kill (pid, SIGKILL);
    int status = 0;
    waitpid (pid, &status, 0);
    return finished && WIFEXITED (status) && WEXITSTATUS (status) == 0 ? output : std::string();
}
}

bool wantsFullScreen (const juce::StringArray& commandLine) { return ! commandLine.contains ("--windowed"); }

std::vector<std::string> fullScreenCommand (unsigned long window)
{
    return { "i3-msg", "-q", "[id=" + std::to_string (window) + "] fullscreen enable" };
}

std::vector<Workspace> parseWorkspaces (const std::string& i3Reply)
{
    // Held in a named var: getArray() points into it (StemDeck, SIGSEGV on the rig, 2026-09-30).
    const auto reply = juce::JSON::parse (juce::String (i3Reply));
    const auto* list = reply.getArray();
    if (list == nullptr)
        return {};
    std::vector<Workspace> out;
    for (const auto& w : *list)
    {
        const auto name = w["name"].toString().toStdString();
        const auto end = digitsEnd (name);
        if (end == 0 || end > 6)   // no number, or one stoi would throw on
            continue;
        const auto label = end < name.size() && name[end] == ':' ? name.substr (end + 1) : name;
        out.push_back ({ std::stoi (name.substr (0, end)), label, (bool) w["focused"] });
    }
    return out;
}

std::vector<std::string> listCommand() { return { "i3-msg", "-t", "get_workspaces" }; }

std::vector<std::string> goToCommand (int number) { return { "i3-msg", "-q", "workspace number " + std::to_string (number) }; }

SwitcherGeometry switcherGeometry (int windowWidth)
{
    const auto share = [windowWidth] (int atRigWidth) { return (int) std::lround (atRigWidth * windowWidth / 768.0); };
    return { share (6), share (30), share (2), share (80), share (40), share (170), share (40), share (4) };
}

I3Runner systemI3Runner()
{
    return [] (const std::vector<std::string>& argv) { return spawnForOutput (argv, i3TimeoutMs); };
}
}
