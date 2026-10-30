// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskComponent.h"
#include "DeskScreen.h"

using namespace desk;

namespace
{
juce::TextButton* workspaceKeyOf (DeskComponent& desk)
{
    for (auto* child : desk.getChildren())
        if (auto* key = dynamic_cast<juce::TextButton*> (child))
            return key;
    return nullptr;
}
}

// As StemDeck: the rig's launch says --fullscreen, a hand-opened desk stays a window.
TEST (DeskScreen, FullScreenOnlyWhenAskedFor)
{
    EXPECT_TRUE (screen::wantsFullScreen (juce::StringArray { "--fullscreen" }));
    EXPECT_TRUE (screen::wantsFullScreen (juce::StringArray { "-x", "--fullscreen" }));
    EXPECT_FALSE (screen::wantsFullScreen (juce::StringArray {}));
    EXPECT_FALSE (screen::wantsFullScreen (juce::StringArray { "--full" }));
}

// i3 is asked as StemDeck asks it (Workspaces.cpp): i3-msg, quiet, one command.
TEST (DeskScreen, TheNextWorkspaceIsI3sNext)
{
    EXPECT_EQ (screen::nextWorkspaceCommand(), (std::vector<std::string> { "i3-msg", "-q", "workspace next" }));
}

// Full screen hides i3's bar: the desk's own key goes on to the next workspace, through the runner it is given.
TEST (DeskScreen, TheWorkspaceKeyRunsI3)
{
    std::vector<std::vector<std::string>> calls;
    DeskComponent desk ([] (const Outgoing&) { return true; });
    desk.setSize (768, 1024);
    auto* key = workspaceKeyOf (desk);
    ASSERT_NE (key, nullptr);
    EXPECT_FALSE (key->isVisible());   // without a runner (the tests, a3-prodj) there is no key
    desk.setWorkspaceRunner ([&calls] (const std::vector<std::string>& argv) { calls.push_back (argv); });
    EXPECT_TRUE (key->isVisible());
    EXPECT_TRUE (key->isEnabled());   // no Core needed: the way out works whatever the desk's state
    ASSERT_TRUE (key->onClick != nullptr);
    key->onClick();
    ASSERT_EQ (calls.size(), 1u);
    EXPECT_EQ (calls[0], screen::nextWorkspaceCommand());
    EXPECT_EQ (key->getBounds(), layOutDesk (desk.getLocalBounds().toFloat(), currentFingertip()).workspace.toNearestInt());
}
