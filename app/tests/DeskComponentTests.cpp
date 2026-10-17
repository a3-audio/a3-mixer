// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskComponent.h"
#include "DeskControls.h"
#include "DeskLink.h"
#include "TestTruth.h"

using namespace desk;

namespace
{
struct Captured
{
    std::vector<Outgoing> sent;
    DeskComponent::Send sink()
    {
        return [this] (const Outgoing& out) {
            sent.push_back (out);
            return true;
        };
    }
    juce::StringArray addresses() const
    {
        juce::StringArray out;
        for (const auto& o : sent)
            out.add (o.message.getAddressPattern().toString());
        return out;
    }
};

const DeskOsc& osc()
{
    static const DeskOsc made (test::truth());
    return made;
}

std::unique_ptr<DeskComponent> deskAtStart (Captured& c)
{
    auto desk = std::make_unique<DeskComponent> (c.sink());
    desk->setSize (620, 1000);
    desk->useTruth (test::truth());
    desk->setLinkState (DeskLink::Opened::ok);
    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-1" }, 0);
    return desk;
}

void answer (DeskComponent& desk, double nowMs)
{
    juce::OSCMessage beat (juce::OSCAddressPattern (osc().address ("beat")), 1, 1, 120.f);
    desk.receive (beat, nowMs);
}

std::unique_ptr<DeskComponent> deskJoined (Captured& c)
{
    auto desk = deskAtStart (c);
    desk->step (0);
    answer (*desk, 100);
    desk->step (100);
    c.sent.clear();
    return desk;
}

/** The test truth without one key the desk sends: what an older Core would serve. */
a3::OscTruth truthWithout (const char* key)
{
    auto data = juce::JSON::parse (juce::File (juce::SystemStats::getEnvironmentVariable ("A3_OSC_TRUTH", {}))
                                       .loadFileAsString());
    if (auto* addresses = data["addresses"].getDynamicObject())
        addresses->removeProperty (key);
    return a3::parseOscTruth (juce::JSON::toString (data));
}
}

TEST (DeskComponent, AtStartItSendsOnlyHelloAndRecall)
{
    Captured c;
    auto desk = deskAtStart (c);
    desk->step (0);
    EXPECT_EQ (c.addresses(), juce::StringArray (osc().address ("device.hello"), osc().address ("state.recall")));
}

// Review focus 2.
TEST (DeskComponent, ControlsTakeNoHandBeforeTheFirstAnswer)
{
    Captured c;
    auto desk = deskAtStart (c);
    desk->step (0);
    c.sent.clear();
    desk->touchPot (potIndex ("channel.gain", 1), 0.5f);
    EXPECT_TRUE (c.sent.empty());
    answer (*desk, 100);
    desk->step (100);
    desk->touchPot (potIndex ("channel.gain", 1), 0.5f);
    EXPECT_EQ (c.addresses(), juce::StringArray (osc().address ("channel.gain", 1)));
}

TEST (DeskComponent, ATouchSendsThePotAndRaisesTheRing)
{
    Captured c;
    auto desk = deskJoined (c);
    const int pot = potIndex ("master.aux-return", 0);
    EXPECT_FALSE (desk->state().marked (pot));
    desk->touchPot (pot, 0.4f);
    ASSERT_EQ (c.sent.size(), 1u);
    ASSERT_EQ (c.sent[0].message.size(), 1);
    EXPECT_FLOAT_EQ (c.sent[0].message[0].getFloat32(), 0.4f);
    EXPECT_TRUE (desk->state().marked (pot));
}

TEST (DeskComponent, TheLockHoldsMasterBoothAndPhones)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->setLocked (true);
    desk->touchPot (potIndex ("master.volume", 0), 0.2f);
    desk->touchPot (potIndex ("master.phones-volume", 0), 0.2f);
    EXPECT_TRUE (c.sent.empty());
    desk->touchPot (potIndex ("filter.frequency", 0), 0.2f);
    EXPECT_EQ (c.sent.size(), 1u);
}

TEST (DeskComponent, OneToFourCueAndSpaceTaps)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->keyPressed (juce::KeyPress ('2'));
    desk->keyPressed (juce::KeyPress (juce::KeyPress::spaceKey));
    ASSERT_EQ (c.sent.size(), 3u);
    ASSERT_EQ (c.sent[0].message.size(), 1);
    ASSERT_EQ (c.sent[1].message.size(), 1);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("channel.cue", 2));
    EXPECT_EQ (c.sent[0].message[0].getString(), "1");
    EXPECT_EQ (c.sent[1].message[0].getString(), "0");
    EXPECT_EQ (c.sent[2].to, Outgoing::To::beatClock);
}

// Review focus 3.
TEST (DeskComponent, ANewCoreIsAskedAgainAndToldNothing)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-2" }, 9000);
    desk->step (9000);
    EXPECT_EQ (c.addresses(), juce::StringArray (osc().address ("device.hello"), osc().address ("state.recall")));
    EXPECT_FALSE (desk->handsAccepted());
}

// DeskWire::to() throws for a key the truth lacks: such a truth must never build a wire.
TEST (DeskComponent, ATruthLackingAKeyWaitsAndSendsNothing)
{
    const auto lacking = truthWithout ("device.hello");
    ASSERT_TRUE (lacking.isValid());
    ASSERT_TRUE (DeskOsc::missing (lacking).contains ("device.hello"));
    Captured c;
    DeskComponent desk (c.sink());
    desk.setSize (620, 1000);
    desk.useTruth (lacking);
    desk.setLinkState (DeskLink::Opened::ok);
    desk.announced ({ "http://core/a3-osc.json", lacking.digest(), "boot-1" }, 0);
    EXPECT_NO_THROW (desk.step (0));
    EXPECT_EQ (desk.osc(), nullptr);
    EXPECT_TRUE (c.sent.empty());
    EXPECT_FALSE (desk.handsAccepted());
    EXPECT_TRUE (desk.statusText().contains ("device.hello"));
}

TEST (DeskComponent, TheWholeWindowPaintsEveryState)
{
    Captured c;
    DeskComponent empty (c.sink());
    empty.setSize (620, 1000);
    empty.step (0);
    const auto waiting = empty.createComponentSnapshot (empty.getLocalBounds());

    auto desk = deskAtStart (c);
    desk->step (0);
    answer (*desk, 100);
    ASSERT_NE (desk->vuInbox(), nullptr);
    for (const auto* name : { "in1_pre_L", "main_sub", "stem_a1", "analog2_R" })
        desk->vuInbox()->note (test::truth().vuNumber (name), 0.9f);
    desk->step (140);
    const auto playing = desk->createComponentSnapshot (desk->getLocalBounds());
    desk->step (7000);   // no /core/here for 5 s: Core silent
    const auto silent = desk->createComponentSnapshot (desk->getLocalBounds());

    EXPECT_TRUE (waiting.isValid());
    const auto brightness = [] (const juce::Image& image) {
        double sum = 0;
        for (int y = 0; y < image.getHeight(); y += 4)
            for (int x = 0; x < image.getWidth(); x += 4)
                sum += image.getPixelAt (x, y).getBrightness();
        return sum;
    };
    EXPECT_GT (brightness (playing), brightness (silent));
    EXPECT_TRUE (desk->statusText().contains ("Core silent"));
}

// 1-4 and Space must work the moment the window is up: the desk wants the
// focus, and none of its controls takes it first -- so a window's focus (its
// peer's, or DeskWindow's grab when shown and activated) lands on the desk.
// (A real DeskWindow needs a window manager; Xvfb has none.)
TEST (DeskComponent, AWindowsFocusGoesToTheDesk)
{
    Captured c;
    juce::Component window;
    DeskComponent desk (c.sink());
    window.addAndMakeVisible (desk);
    EXPECT_TRUE (desk.getWantsKeyboardFocus());
    const auto traverser = window.createKeyboardFocusTraverser();
    ASSERT_NE (traverser, nullptr);
    EXPECT_EQ (traverser->getDefaultComponent (&window), &desk);
}

/** The pot's control: the pots are the desk's first children, in allPots() order. */
juce::Slider* potControl (DeskComponent& desk, int pot)
{
    return dynamic_cast<juce::Slider*> (desk.getChildComponent (pot));
}

// A slider disabled mid-drag never sends onDragEnd: losing the hands must release the grab.
TEST (DeskComponent, LosingTheHandsMidDragReleasesThePot)
{
    Captured c;
    auto desk = deskJoined (c);
    const int pot = potIndex ("channel.gain", 1);
    auto* control = potControl (*desk, pot);
    ASSERT_NE (control, nullptr);
    ASSERT_TRUE (control->onDragStart != nullptr);
    control->onDragStart();
    ASSERT_TRUE (desk->state().grabbed (pot));
    desk->step (7000);   // Core silent: the hands go
    juce::OSCMessage relay (juce::OSCAddressPattern (osc().address ("channel.gain", 1)), 0.7f);
    desk->receive (relay, 7000);
    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-1" }, 7100);
    desk->step (7100);
    answer (*desk, 7200);
    desk->step (7200);
    ASSERT_TRUE (desk->handsAccepted());
    EXPECT_FALSE (desk->state().grabbed (pot));
    EXPECT_NEAR (control->getValue(), 0.7, 1e-6);
}

// Final review I1: back from silence is a new start -- hello and recall at once,
// and no hand until Core has answered (what it sent meanwhile is lost).
TEST (DeskComponent, BackFromSilenceAsksAgainAndTakesNoHandUntilAnswered)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->step (7000);   // Core silent
    c.sent.clear();
    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-1" }, 7100);
    desk->step (7100);
    EXPECT_EQ (c.addresses(), juce::StringArray (osc().address ("device.hello"), osc().address ("state.recall")));
    EXPECT_FALSE (desk->handsAccepted());
    c.sent.clear();
    desk->touchPot (potIndex ("channel.gain", 1), 0.5f);
    EXPECT_TRUE (c.sent.empty());
    answer (*desk, 7200);
    desk->step (7200);
    EXPECT_TRUE (desk->handsAccepted());
}

// Stale dims the whole surface (spec 4.1): every child but the status line, LOCK too.
TEST (DeskComponent, CoreSilentDimsEveryControl)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->step (7000);
    ASSERT_FALSE (desk->handsAccepted());
    int enabled = 0;
    for (auto* child : desk->getChildren())
        if (child->isEnabled() && dynamic_cast<StatusLine*> (child) == nullptr)
            ++enabled;
    EXPECT_EQ (enabled, 0);
}

// Held keys autorepeat: only the first press acts, and Ctrl/Alt+1-4 is not a CUE.
TEST (DeskComponent, AHeldKeyActsOnce)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->keyPressed (juce::KeyPress ('2'));
    desk->keyPressed (juce::KeyPress ('2'));
    desk->keyPressed (juce::KeyPress (juce::KeyPress::spaceKey));
    desk->keyPressed (juce::KeyPress (juce::KeyPress::spaceKey));
    EXPECT_EQ (c.sent.size(), 3u);   // CUE 2 press + release, one TAP
    desk->keyStateChanged (false);   // released (no key is down in the test)
    c.sent.clear();
    desk->keyPressed (juce::KeyPress ('2'));
    EXPECT_EQ (c.sent.size(), 2u);
    desk->keyStateChanged (false);
    c.sent.clear();
    desk->keyPressed (juce::KeyPress ('3', juce::ModifierKeys::ctrlModifier, 0));
    desk->keyPressed (juce::KeyPress ('3', juce::ModifierKeys::altModifier, 0));
    EXPECT_TRUE (c.sent.empty());
}

// A Core announcing another truth never gets a hello: the status must say why the desk waits.
TEST (DeskComponent, TheStatusSaysCoreServesAnotherTruth)
{
    Captured c;
    DeskComponent desk (c.sink());
    desk.setSize (620, 1000);
    desk.useTruth (test::truth());
    desk.setLinkState (DeskLink::Opened::ok);
    desk.announced ({ "http://core/a3-osc.json", "another-fingerprint", "boot-1" }, 0);
    desk.step (0);
    EXPECT_TRUE (c.sent.empty());
    EXPECT_TRUE (desk.statusText().contains ("another truth"));
}

// Review focus 5.
TEST (DeskLink, ASecondBindOnTheSamePortFails)
{
    juce::DatagramSocket first (false), second (false);
    ASSERT_TRUE (bindExclusively (first, 0));
    ASSERT_GT (first.getBoundPort(), 0);
    EXPECT_FALSE (bindExclusively (second, first.getBoundPort()));
}

TEST (DeskLink, TheStatusSaysWhyItCannotRun)
{
    EXPECT_TRUE (statusFor (DeskLink::Opened::portTaken).contains ("another desk"));
    EXPECT_TRUE (statusFor (DeskLink::Opened::ok).isEmpty());
    EXPECT_TRUE (statusFor (DeskLink::Opened::noSender).contains ("cannot send"));
}
