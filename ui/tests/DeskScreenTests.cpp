// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskComponent.h"
#include "DeskScreen.h"
#include "DeskWorkspaceSwitch.h"
#include "FakePeer.h"

using namespace desk;

namespace
{
using Source = juce::MouseInputSource::InputSourceType;
using Argv = std::vector<std::string>;

const std::string rigWorkspaces =
    R"([{"name":"1:MOTION","focused":false},{"name":"2:STEMDECK","focused":false},{"name":"7:DESK","focused":true}])";

/** The desk on a window of its own, as on the rig, with a fake i3 that notes every command. */
struct OnTheRig
{
    std::vector<Argv> calls;
    std::string reply = rigWorkspaces;
    DeskComponent desk { [] (const Outgoing&) { return true; } };
    test::PeerHost window;
    juce::ComponentPeer* peer = nullptr;

    OnTheRig()
    {
        desk.setSize (768, 1024);
        desk.setWorkspaceRunner ([this] (const Argv& argv) {
            calls.push_back (argv);
            return argv.size() > 1 && argv[1] == "-t" ? reply : std::string();
        });
        window.setBounds (desk.getLocalBounds());
        window.addAndMakeVisible (desk);
        window.addToDesktop (0);
        window.setVisible (true);
        peer = window.getPeer();
    }
    ~OnTheRig() { window.removeChildComponent (&desk); }

    WorkspaceSwitch& keys() { return *desk.workspaceSwitch(); }

    void down (Source s, juce::Point<float> at, juce::int64 t)
    {
        peer->handleMouseEvent (s, at, juce::ModifierKeys (juce::ModifierKeys::leftButtonModifier), 1.f, 0.f, t);
    }
    void up (Source s, juce::Point<float> at, juce::int64 t) { peer->handleMouseEvent (s, at, juce::ModifierKeys(), 1.f, 0.f, t); }

    /** One finger as the rig's X delivers it: touch#0, X's emulated mouse#0 2 ms later. */
    void tap (juce::Point<float> at, juce::int64 t)
    {
        down (Source::touch, at, t);
        down (Source::mouse, at, t + 2);
        up (Source::touch, at, t + 60);
        up (Source::mouse, at, t + 62);
    }
    /** A quick tap: the finger is up before X's copy goes down. */
    void quickTap (juce::Point<float> at, juce::int64 t)
    {
        down (Source::touch, at, t);
        up (Source::touch, at, t + 1);
        down (Source::mouse, at, t + 2);
        up (Source::mouse, at, t + 3);
    }
    static juce::Point<float> centreOf (const juce::Component& c)
    {
        return c.getScreenBounds().getCentre().toFloat() - c.getTopLevelComponent()->getScreenPosition().toFloat();
    }
    std::vector<Argv> workspaceCommands() const
    {
        std::vector<Argv> out;
        for (const auto& c : calls)
            if (c.size() == 3 && c[1] == "-q")
                out.push_back (c);
        return out;
    }
};
}

// As StemDeck: the rig's launch says --fullscreen; full screen is also the default, so the desk is full
// screen however it is started (launcher, Canvas, a unit). --windowed keeps a window.
TEST (DeskScreen, FullScreenUnlessAskedForAWindow)
{
    EXPECT_TRUE (screen::wantsFullScreen (juce::StringArray { "--fullscreen" }));
    EXPECT_TRUE (screen::wantsFullScreen (juce::StringArray {}));
    EXPECT_FALSE (screen::wantsFullScreen (juce::StringArray { "--windowed" }));
}

// JUCE's setFullScreen is a maximise to i3, which tiles it under the bar: i3 is asked for its own full screen,
// on this window.
TEST (DeskScreen, I3IsAskedForFullScreenOnTheWindow)
{
    EXPECT_EQ (screen::fullScreenCommand (0x1a00007), (Argv { "i3-msg", "-q", "[id=27262983] fullscreen enable" }));
}

// i3's answer as StemDeck's Workspaces.cpp reads it: "3:REAPER" -> 3, REAPER; a name without a number is left out.
TEST (DeskScreen, TheWorkspacesAreI3s)
{
    const auto list = screen::parseWorkspaces (
        R"([{"name":"1:MOTION","focused":false},{"name":"7:DESK","focused":true},{"name":"scratch","focused":false}])");
    ASSERT_EQ (list.size(), 2u);
    EXPECT_EQ (list[0].number, 1);
    EXPECT_EQ (list[0].label, "MOTION");
    EXPECT_FALSE (list[0].current);
    EXPECT_EQ (list[1].number, 7);
    EXPECT_EQ (list[1].label, "DESK");
    EXPECT_TRUE (list[1].current);
    EXPECT_TRUE (screen::parseWorkspaces ("").empty());
    EXPECT_EQ (screen::goToCommand (2), (Argv { "i3-msg", "-q", "workspace number 2" }));
}

// StemDeck's and A3 Motion's switch: STEMDECK, then the arrow, at the window's right edge where they have it
// (switcherGeometry: StemDeck's sizes at the rig's 768 px). Without a runner (tests, a3-prodj) there is none.
TEST (DeskWorkspaceSwitch, StemDeckThenTheArrowAtTheRightEdge)
{
    OnTheRig rig;
    auto& keys = rig.keys();
    EXPECT_TRUE (keys.appKey().isVisible());
    EXPECT_TRUE (keys.arrowKey().isVisible());
    EXPECT_EQ (keys.appKey().label(), "STEMDECK");
    EXPECT_EQ (keys.arrowKey().label(), juce::String::fromUTF8 ("\xe2\x96\xbe"));
    const auto g = screen::switcherGeometry (768);
    EXPECT_EQ (g.margin, 6);
    EXPECT_EQ (keys.arrowKey().getRight(), 768 - g.margin);
    EXPECT_EQ (keys.arrowKey().getWidth(), g.arrowWidth);
    EXPECT_EQ (keys.appKey().getRight(), keys.arrowKey().getX() - g.gap);
    EXPECT_EQ (keys.appKey().getWidth(), g.appKeyWidth);
    EXPECT_TRUE (keys.appKey().isEnabled());   // the way out works whatever Core does

    DeskComponent bare ([] (const Outgoing&) { return true; });
    EXPECT_EQ (bare.workspaceSwitch(), nullptr);
}

// Its default choice is StemDeck: one tap, delivered twice by X, is one command.
TEST (DeskWorkspaceSwitch, OneTapOnStemDeckGoesThereOnce)
{
    OnTheRig rig;
    rig.tap (OnTheRig::centreOf (rig.keys().appKey()), 1000);
    EXPECT_EQ (rig.workspaceCommands(), (std::vector<Argv> { screen::goToCommand (2) }));
    rig.calls.clear();
    rig.quickTap (OnTheRig::centreOf (rig.keys().appKey()), 2000);
    EXPECT_EQ (rig.workspaceCommands(), (std::vector<Argv> { screen::goToCommand (2) }));
}

// The arrow opens the list with one tap -- however X delivers it -- and the list stays open; a key in it
// goes to its workspace once and closes it; a tap beside it only closes it.
TEST (DeskWorkspaceSwitch, OneTapOpensTheListAndOneChooses)
{
    for (const bool quick : { false, true })
    {
        OnTheRig rig;
        auto& keys = rig.keys();
        const auto arrow = OnTheRig::centreOf (keys.arrowKey());
        quick ? rig.quickTap (arrow, 1000) : rig.tap (arrow, 1000);
        ASSERT_TRUE (keys.panel().isVisible()) << quick;
        ASSERT_EQ (keys.panel().keyCount(), 3) << quick;
        EXPECT_TRUE (keys.panel().keyAt (2).current());   // 7:DESK
        EXPECT_EQ (keys.panel().keyAt (1).label(), "STEMDECK");
        EXPECT_TRUE (rig.workspaceCommands().empty());

        quick ? rig.quickTap (OnTheRig::centreOf (keys.panel().keyAt (0)), 2000)
              : rig.tap (OnTheRig::centreOf (keys.panel().keyAt (0)), 2000);
        EXPECT_EQ (rig.workspaceCommands(), (std::vector<Argv> { screen::goToCommand (1) })) << quick;
        EXPECT_FALSE (keys.panel().isVisible()) << quick;

        rig.tap (arrow, 3000);
        ASSERT_TRUE (keys.panel().isVisible());
        rig.tap ({ 100.f, 600.f }, 4000);
        EXPECT_FALSE (keys.panel().isVisible());
        EXPECT_EQ (rig.workspaceCommands().size(), 1u);
    }
}

TEST (DeskWorkspaceSwitch, NoAnswerFromI3KeepsTheListClosed)
{
    OnTheRig rig;
    rig.reply.clear();
    rig.tap (OnTheRig::centreOf (rig.keys().arrowKey()), 1000);
    EXPECT_FALSE (rig.keys().panel().isVisible());
}
