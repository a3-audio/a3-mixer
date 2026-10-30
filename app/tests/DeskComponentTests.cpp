// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <functional>

#include <gtest/gtest.h>

#include "DeskComponent.h"
#include "DeskControls.h"
#include "DeskDelay.h"
#include "DeskLink.h"
#include "FakePeer.h"
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

std::unique_ptr<DeskComponent> deskAtStart (Captured& c, const juce::String& device = "desk")
{
    auto desk = std::make_unique<DeskComponent> (c.sink(), device);
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
a3::OscTruth truthWithout (const std::vector<std::string>& keys)
{
    auto data = juce::JSON::parse (juce::File (juce::SystemStats::getEnvironmentVariable ("A3_OSC_TRUTH", {}))
                                       .loadFileAsString());
    if (auto* addresses = data["addresses"].getDynamicObject())
        for (const auto& key : keys)
            addresses->removeProperty (juce::Identifier (key));
    return a3::parseOscTruth (juce::JSON::toString (data));
}

a3::OscTruth truthWithout (const char* key) { return truthWithout (std::vector<std::string> { key }); }

/** What a Core from before the delay list serves (R25). */
a3::OscTruth truthWithoutTheDelay() { return truthWithout (delay::delayKeys()); }
}

namespace
{
/** Joined on a truth of the test's choosing (the desk's own helpers take the runner's). */
std::unique_ptr<DeskComponent> deskJoinedOn (Captured& c, const a3::OscTruth& truth)
{
    auto desk = std::make_unique<DeskComponent> (c.sink(), "desk");
    desk->setSize (620, 1000);
    desk->useTruth (truth);
    desk->setLinkState (DeskLink::Opened::ok);
    desk->announced ({ "http://core/a3-osc.json", truth.digest(), "boot-1" }, 0);
    desk->step (0);
    juce::OSCMessage beat (juce::OSCAddressPattern (DeskOsc (truth).address ("beat")), 1, 1, 120.f);
    desk->receive (beat, 100);
    desk->step (100);
    c.sent.clear();
    return desk;
}

StatusLine* statusLineOf (DeskComponent& desk)
{
    for (auto* child : desk.getChildren())
        if (auto* line = dynamic_cast<StatusLine*> (child))
            return line;
    return nullptr;
}

juce::Point<float> liveChipCentre (DeskComponent& desk)
{
    auto* line = statusLineOf (desk);
    return line == nullptr ? juce::Point<float>() : (line->getPosition().toFloat() + line->liveChip().getCentre());
}

void liveSays (DeskComponent& desk, int value, double nowMs)
{
    juce::OSCMessage m (juce::OSCAddressPattern ("/prodj/live"), value);
    desk.receive (m, nowMs);
}
}

TEST (DeskComponent, TheLiveChipTogglesWithHands)
{
    Captured c;
    const auto truth = test::truthWithLive (true);
    auto desk = deskJoinedOn (c, truth);
    auto* line = statusLineOf (*desk);
    ASSERT_NE (line, nullptr);
    ASSERT_TRUE (static_cast<bool> (line->onLiveTapped));
    line->onLiveTapped();
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), "/prodj/live");
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 1);

    liveSays (*desk, 1, 200);   // Core says so: lit
    desk->step (200);
    c.sent.clear();
    line->onLiveTapped();
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 0);
}

TEST (DeskComponent, TheLiveChipSendsNothingWithoutHands)
{
    Captured c;
    const auto truth = test::truthWithLive (true);
    auto desk = deskJoinedOn (c, truth);
    auto* line = statusLineOf (*desk);
    ASSERT_NE (line, nullptr);
    desk->setHandsWithheld (true);
    line->onLiveTapped();
    EXPECT_TRUE (c.sent.empty());

    Captured c2;
    auto notJoined = std::make_unique<DeskComponent> (c2.sink(), "desk");
    notJoined->setSize (620, 1000);
    notJoined->useTruth (truth);
    notJoined->setLinkState (DeskLink::Opened::ok);
    notJoined->step (0);
    c2.sent.clear();
    ASSERT_NE (statusLineOf (*notJoined), nullptr);
    if (statusLineOf (*notJoined)->onLiveTapped)
        statusLineOf (*notJoined)->onLiveTapped();
    EXPECT_TRUE (c2.sent.empty());
}

TEST (DeskComponent, TheDeskNeverSendsLiveOnItsOwn)
{
    Captured c;
    auto desk = deskJoinedOn (c, test::truthWithLive (true));
    liveSays (*desk, 1, 200);
    for (double t = 300; t < 40000; t += 1000)
        desk->step (t);
    for (const auto& address : c.addresses())
        EXPECT_NE (address, "/prodj/live");
}

TEST (DeskComponent, ATruthWithoutLiveHasNoChipAndSendsNothing)
{
    Captured c;
    auto desk = deskJoinedOn (c, test::truthWithLive (false));
    auto* line = statusLineOf (*desk);
    ASSERT_NE (line, nullptr);
    EXPECT_TRUE (line->liveChip().isEmpty());
    if (line->onLiveTapped)
        line->onLiveTapped();
    EXPECT_TRUE (c.sent.empty());
}

TEST (DeskComponent, TheChipLightsWhileLiveAndGoesDarkWhenTheLeaseRunsOut)
{
    Captured c;
    auto desk = deskJoinedOn (c, test::truthWithLive (true));
    auto* line = statusLineOf (*desk);
    ASSERT_NE (line, nullptr);
    const auto chip = line->liveChip().toNearestInt();
    ASSERT_FALSE (chip.isEmpty());
    const auto shot = [&] { return line->createComponentSnapshot (chip, false, 1.f); };
    const auto light = [] (const juce::Image& image) {
        double sum = 0.0;
        for (int y = 0; y < image.getHeight(); ++y)
            for (int x = 0; x < image.getWidth(); ++x)
                sum += static_cast<double> (image.getPixelAt (x, y).getPerceivedBrightness());
        return sum;
    };
    const auto before = light (shot());
    liveSays (*desk, 1, 200);
    desk->step (200);
    const auto lit = light (shot());
    EXPECT_GT (lit, before);
    for (double t = 3000; t <= 12000; t += 3000)   // Core is still there, only the LIVE repeat is not
        desk->announced ({ "http://core/a3-osc.json", test::truthWithLive (true).digest(), "boot-1" }, t);
    desk->step (12300);   // the lease is out
    EXPECT_DOUBLE_EQ (light (shot()), before);
}

TEST (DeskComponent, HelloCarriesTheDeviceName)
{
    Captured c;
    auto desk = deskAtStart (c, "prodj");
    desk->step (0);
    ASSERT_FALSE (c.sent.empty());
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("device.hello"));
    EXPECT_EQ (c.sent[0].message[0].getString(), "prodj");
}

TEST (DeskComponent, NoHandsWhileWithheld)
{
    Captured c;
    auto desk = deskJoined (c);
    ASSERT_TRUE (desk->handsAccepted());
    desk->setHandsWithheld (true);
    EXPECT_FALSE (desk->handsAccepted());
    desk->step (200);   // every control dims, as before Core answers
    for (const auto* key : { "channel.volume", "channel.cue" })
    {
        ASSERT_NE (desk->controlFor (key, 1), nullptr) << key;
        EXPECT_FALSE (desk->controlFor (key, 1)->isEnabled());
    }
    ASSERT_NE (desk->controlFor ("master.booth", 0), nullptr);
    EXPECT_FALSE (desk->controlFor ("master.booth", 0)->isEnabled());
    desk->keyPressed (juce::KeyPress ('2'));   // CUE 2 from the keyboard
    EXPECT_TRUE (c.sent.empty());
    auto* cue = dynamic_cast<DeskKey*> (desk->controlFor ("channel.cue", 2));
    ASSERT_NE (cue, nullptr);
    cue->onPress (true);
    EXPECT_TRUE (c.sent.empty());
    desk->touchPot (potIndex ("channel.gain", 1), 0.5f);
    EXPECT_TRUE (c.sent.empty());
    desk->setHandsWithheld (false);
    EXPECT_TRUE (desk->handsAccepted());
    desk->step (300);
    ASSERT_NE (desk->controlFor ("channel.cue", 1), nullptr);
    EXPECT_TRUE (desk->controlFor ("channel.cue", 1)->isEnabled());
    desk->touchPot (potIndex ("channel.gain", 1), 0.5f);
    EXPECT_EQ (c.sent.size(), 1u);
}

TEST (DeskComponent, ControlForFindsTheFaderAndTheCue)
{
    Captured c;
    auto desk = deskAtStart (c);
    auto* fader = desk->controlFor ("channel.volume", 2);
    ASSERT_NE (fader, nullptr);
    EXPECT_NE (dynamic_cast<DeskFader*> (fader), nullptr);
    auto* cue = desk->controlFor ("channel.cue", 3);
    ASSERT_NE (cue, nullptr);
    EXPECT_NE (dynamic_cast<DeskKey*> (cue), nullptr);
    EXPECT_NE (desk->controlFor ("channel.cue", 3), desk->controlFor ("channel.cue", 2));
    EXPECT_EQ (desk->controlFor ("nope", 1), nullptr);
    EXPECT_EQ (desk->controlFor ("channel.volume", 9), nullptr);
}

// Ruling R15: every control with a truth key, or a lamp word arriving for it would never glow.
TEST (DeskComponent, ControlForCoversEveryControlWithAKey)
{
    Captured c;
    auto desk = deskAtStart (c);
    const auto is = [&] (const char* key, int channel, auto* type) {
        auto* control = desk->controlFor (key, channel);
        EXPECT_NE (control, nullptr) << key << " " << channel;
        return control != nullptr && dynamic_cast<decltype (type)> (control) != nullptr;
    };
    EXPECT_TRUE (is ("master.booth", 0, (DeskKnob*) nullptr));
    EXPECT_TRUE (is ("channel.gain", 4, (DeskKnob*) nullptr));
    EXPECT_TRUE (is ("channel.filter", 1, (DeskKey*) nullptr));
    EXPECT_TRUE (is ("tap", 0, (DeskKey*) nullptr));   // one TAP, the fourth strip's
    EXPECT_TRUE (is ("channel.stem.turn", 3, (DeskEncoder*) nullptr));
    EXPECT_TRUE (is ("channel.stem.push", 3, (DeskEncoder*) nullptr));
    EXPECT_EQ (desk->controlFor ("channel.stem.turn", 3), desk->controlFor ("channel.stem.push", 3));
    EXPECT_TRUE (is ("aux-return.stem.push", 0, (DeskKey*) nullptr));   // DELAY CUE
    for (const auto* turn : { "aux-return.delay.beat.turn", "aux-return.delay.feedback.turn", "aux-return.delay.color.turn",
                              "aux-return.delay.spread.turn" })
        EXPECT_TRUE (is (turn, 0, (DeskEncoder*) nullptr)) << turn;   // SELECT walks the delay list
    EXPECT_EQ (desk->controlFor ("aux-return.stem.turn", 0), nullptr);
    EXPECT_TRUE (is ("filter.mode", 1, (DeskKey*) nullptr));   // 1 = HPF, 2 = LPF: one word, two keys
    EXPECT_TRUE (is ("filter.mode", 2, (DeskKey*) nullptr));
    EXPECT_NE (desk->controlFor ("filter.mode", 1), desk->controlFor ("filter.mode", 2));
    EXPECT_EQ (desk->controlFor ("filter.mode", 0), nullptr);
    EXPECT_EQ (desk->controlFor ("tap", 5), nullptr);
    EXPECT_EQ (desk->controlFor ("tap", 2), nullptr);
}

TEST (DeskComponent, MetersAreThere)
{
    Captured c;
    auto desk = std::make_unique<DeskComponent> (c.sink());
    EXPECT_EQ (desk->meters(), nullptr);
    desk->useTruth (test::truth());
    EXPECT_NE (desk->meters(), nullptr);
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

// Stale dims the whole surface (spec 4.1): every child but the status line and the way to the next workspace.
TEST (DeskComponent, CoreSilentDimsEveryControl)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->step (7000);
    ASSERT_FALSE (desk->handsAccepted());
    int enabled = 0;
    for (auto* child : desk->getChildren())
        if (child->isEnabled() && dynamic_cast<StatusLine*> (child) == nullptr && dynamic_cast<juce::TextButton*> (child) == nullptr)
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

namespace
{
juce::MouseEvent clickOn (juce::Component& c, juce::Point<float> at, juce::Point<float> downAt, bool dragged)
{
    return { juce::Desktop::getInstance().getMainMouseSource(), at, juce::ModifierKeys(), 1.f,
             juce::MouseInputSource::defaultOrientation, juce::MouseInputSource::defaultRotation,
             juce::MouseInputSource::defaultTiltX, juce::MouseInputSource::defaultTiltY, &c, &c,
             juce::Time::getCurrentTime(), downAt, juce::Time::getCurrentTime(), 2, dragged };
}

/** What a drag to `value` would have sent for this pot. */
Outgoing dragTo (int pot, float value)
{
    const DeskWire wire (osc());
    return wire.pot (pot, value);
}

/** The n-th child of a kind, in the order the desk built them (channel strips first). */
template <typename Kind>
Kind* nthChild (DeskComponent& desk, int n)
{
    for (auto* child : desk.getChildren())
        if (auto* found = dynamic_cast<Kind*> (child); found != nullptr && n-- == 0)
            return found;
    return nullptr;
}
}

// The maintainer, smoke test 2026-10-17: "double-tap should reset to the default value".
// The reset is a hand on the pot: grabbed, sent as a drag would send it, ringed, released.
TEST (DeskComponent, TwoTapsPutEachKindOfPotBackAsADragWould)
{
    for (const auto& [key, channel] : std::vector<std::pair<std::string, int>> {
             { "channel.gain", 1 }, { "channel.eq.mid", 2 }, { "channel.volume", 3 }, { "channel.aux-send", 4 },
             { "filter.frequency", 0 }, { "master.phones-mix", 0 }, { "master.aux-return", 0 } })
    {
        Captured c;
        auto desk = deskJoined (c);
        const int pot = potIndex (key, channel);
        auto* control = potControl (*desk, pot);
        ASSERT_NE (control, nullptr) << key;
        desk->touchPot (pot, 0.3f);
        c.sent.clear();
        const auto centre = control->getLocalBounds().getCentre().toFloat();
        control->mouseDoubleClick (clickOn (*control, centre, centre, false));
        const auto rest = *restPosition (key);
        ASSERT_EQ (c.sent.size(), 1u) << key;
        const auto expected = dragTo (pot, rest);
        EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), expected.message.getAddressPattern().toString());
        ASSERT_TRUE (c.sent[0].message[0].isFloat32()) << key;
        EXPECT_FLOAT_EQ (c.sent[0].message[0].getFloat32(), rest) << key;
        EXPECT_FLOAT_EQ (desk->state().value (pot), rest) << key;
        EXPECT_TRUE (desk->state().marked (pot)) << key;
        EXPECT_FALSE (desk->state().grabbed (pot)) << key;
    }
}

TEST (DeskComponent, TwoTapsLeaveMasterBoothAndPhonesWhereTheyAre)
{
    Captured c;
    auto desk = deskJoined (c);
    for (const auto* key : { "master.volume", "master.booth", "master.phones-volume" })
    {
        const int pot = potIndex (key, 0);
        desk->touchPot (pot, 0.3f);
        c.sent.clear();
        auto* control = potControl (*desk, pot);
        const auto centre = control->getLocalBounds().getCentre().toFloat();
        control->mouseDoubleClick (clickOn (*control, centre, centre, false));
        EXPECT_TRUE (c.sent.empty()) << key;
        EXPECT_FLOAT_EQ (desk->state().value (pot), 0.3f) << key;
    }
}

namespace
{
using Source = juce::MouseInputSource::InputSourceType;

/** One finger down and up as the rig's X delivers it: through the window's peer, by source. */
void press (juce::ComponentPeer& peer, Source source, juce::Point<float> at, juce::int64 timeMs)
{
    peer.handleMouseEvent (source, at, juce::ModifierKeys (juce::ModifierKeys::leftButtonModifier), 1.f, 0.f, timeMs);
}

void lift (juce::ComponentPeer& peer, Source source, juce::Point<float> at, juce::int64 timeMs)
{
    peer.handleMouseEvent (source, at, juce::ModifierKeys(), 1.f, 0.f, timeMs);
}

/** A tap of one finger on the rig: touch#0, and 2 ms later X's emulated mouse#0 (memory: every touch arrives twice). */
void tapTwiceDelivered (juce::ComponentPeer& peer, juce::Point<float> at, juce::int64 t)
{
    press (peer, Source::touch, at, t);
    press (peer, Source::mouse, at, t + 2);
    lift (peer, Source::touch, at, t + 60);
    lift (peer, Source::mouse, at, t + 62);
}
}

// JUCE counts clicks per input source, so the rig's double delivery of one
// finger is never two taps -- and a real double tap still resets, once.
TEST (DeskComponent, OneTapArrivingTwiceIsNoDoubleTap)
{
    Captured c;
    auto desk = deskJoined (c);
    test::PeerHost window;
    window.setBounds (desk->getLocalBounds());
    window.addAndMakeVisible (*desk);
    window.addToDesktop (0);
    window.setVisible (true);   // an invisible window has nothing under the finger
    auto* peer = window.getPeer();
    ASSERT_NE (peer, nullptr);
    const int pot = potIndex ("channel.eq.high", 2);
    desk->touchPot (pot, 0.3f);
    c.sent.clear();
    const auto at = potControl (*desk, pot)->getBounds().getCentre().toFloat();

    tapTwiceDelivered (*peer, at, 10000);
    EXPECT_TRUE (c.sent.empty());
    EXPECT_FLOAT_EQ (desk->state().value (pot), 0.3f);

    tapTwiceDelivered (*peer, at, 20000);
    tapTwiceDelivered (*peer, at, 20200);
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_FLOAT_EQ (c.sent[0].message[0].getFloat32(), 0.5f);
    window.removeChildComponent (desk.get());
}

// Smoke test 2026-10-17: "the encoder for display control is missing on the channels".
// The channel encoder is the hardware's (a3_mixer_encoders): a turn sends
// channel.stem.turn with the clicks, a press channel.stem.push 1.
TEST (DeskComponent, TheChannelEncoderSendsTheHardwaresTurnAndPush)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* encoder = nthChild<DeskEncoder> (*desk, 1);   // channel 2's
    ASSERT_NE (encoder, nullptr);
    const juce::Point<float> start { encoder->getWidth() * 0.5f, encoder->getHeight() * 0.5f };
    const float click = turns::dragPerClickOfKnob * static_cast<float> (encoder->getHeight());
    encoder->mouseDown (clickOn (*encoder, start, start, false));
    encoder->mouseDrag (clickOn (*encoder, start.translated (0.f, -2.5f * click), start, true));
    encoder->mouseUp (clickOn (*encoder, start.translated (0.f, -2.5f * click), start, true));
    encoder->mouseDown (clickOn (*encoder, start, start, false));
    encoder->mouseUp (clickOn (*encoder, start, start, false));
    encoder->mouseWheelMove (clickOn (*encoder, start, start, false), juce::MouseWheelDetails { 0.f, -0.1f, false, false, false });

    ASSERT_EQ (c.sent.size(), 3u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("channel.stem.turn", 2));
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 2);
    EXPECT_EQ (c.sent[1].message.getAddressPattern().toString(), osc().address ("channel.stem.push", 2));
    EXPECT_EQ (c.sent[1].message[0].getInt32(), 1);
    EXPECT_EQ (c.sent[2].message[0].getInt32(), -1);
}

// R25, as the hardware: on a truth without the delay words the FX Return has nothing to choose. Its
// encoder's turn sends nothing, its press the cue (aux-return.stem.push 1); on its display only the CUE
// field answers a tap, with the same word.
TEST (DeskComponent, WithoutTheDelayWordsTheReturnEncoderOnlyCues)
{
    Captured c;
    auto desk = deskJoinedOn (c, truthWithoutTheDelay());
    auto* encoder = nthChild<DeskEncoder> (*desk, numChannels);   // SELECT, after the four channels'
    ASSERT_NE (encoder, nullptr);
    const juce::Point<float> start { encoder->getWidth() * 0.5f, encoder->getHeight() * 0.5f };
    const float click = turns::dragPerClickOfKnob * static_cast<float> (encoder->getHeight());
    encoder->mouseDown (clickOn (*encoder, start, start, false));
    encoder->mouseDrag (clickOn (*encoder, start.translated (0.f, -2.5f * click), start, true));
    encoder->mouseUp (clickOn (*encoder, start.translated (0.f, -2.5f * click), start, true));
    encoder->mouseWheelMove (clickOn (*encoder, start, start, false), juce::MouseWheelDetails { 0.f, -0.1f, false, false, false });
    EXPECT_TRUE (c.sent.empty());
    encoder->mouseDown (clickOn (*encoder, start, start, false));
    encoder->mouseUp (clickOn (*encoder, start, start, false));
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("aux-return.stem.push"));
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 1);

    auto* display = nthChild<OledView> (*desk, numChannels);
    ASSERT_NE (display, nullptr);
    c.sent.clear();
    display->onSlot (0);   // the meter
    EXPECT_TRUE (c.sent.empty());
    display->onSlot (1);   // the CUE field, after the one meter
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("aux-return.stem.push"));
}

// The display shows the selection Core reports, not the desk's own count of clicks.
TEST (DeskComponent, TheChannelDisplayFollowsCoresCursor)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* display = nthChild<OledView> (*desk, 1);
    ASSERT_NE (display, nullptr);
    desk->step (140);
    const auto before = display->createComponentSnapshot (display->getLocalBounds());
    juce::OSCMessage cursor (juce::OSCAddressPattern (osc().address ("channel.source.cursor", 2)), 2);
    desk->receive (cursor, 150);
    desk->step (180);
    const auto after = display->createComponentSnapshot (display->getLocalBounds());
    int differing = 0;
    for (int y = 0; y < before.getHeight(); ++y)
        for (int x = 0; x < before.getWidth(); ++x)
            differing += before.getPixelAt (x, y) != after.getPixelAt (x, y) ? 1 : 0;
    EXPECT_GT (differing, 0);
}

// The hardware's encoder sits right under its display, a cap at least a pot's
// size (V02 photo): the virtual one must be found there, not read as a pot.
TEST (DeskComponent, TheEncoderHangsUnderItsDisplay)
{
    Captured c;
    auto desk = deskJoined (c);
    for (int ch = 0; ch < numChannels; ++ch)
    {
        auto* encoder = nthChild<DeskEncoder> (*desk, ch);
        auto* display = nthChild<OledView> (*desk, ch);
        ASSERT_NE (encoder, nullptr);
        EXPECT_NEAR (encoder->getBounds().getCentreX(), display->getBounds().getCentreX(), 1.0);
        EXPECT_LE (std::abs (encoder->getY() - display->getBottom()), 1);
    }
}

// One finger arrives as touch#0 and X's emulated mouse#0: the chip acts once.
TEST (DeskComponent, OneTapOnTheLiveChipArrivingTwiceSendsOnce)
{
    Captured c;
    auto desk = deskJoinedOn (c, test::truthWithLive (true));
    test::PeerHost window;
    window.setBounds (desk->getLocalBounds());
    window.addAndMakeVisible (*desk);
    window.addToDesktop (0);
    window.setVisible (true);
    auto* peer = window.getPeer();
    ASSERT_NE (peer, nullptr);
    c.sent.clear();
    tapTwiceDelivered (*peer, liveChipCentre (*desk), 10000);
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 1);
    window.removeChildComponent (desk.get());
}

namespace
{
juce::Image displayShot (DeskComponent& desk, int channelIndex)
{
    return nthChild<OledView> (desk, channelIndex)->createComponentSnapshot (
        nthChild<OledView> (desk, channelIndex)->getLocalBounds());
}

bool samePixels (const juce::Image& a, const juce::Image& b)
{
    if (a.getWidth() != b.getWidth() || a.getHeight() != b.getHeight())
        return false;
    for (int y = 0; y < a.getHeight(); ++y)
        for (int x = 0; x < a.getWidth(); ++x)
            if (a.getPixelAt (x, y) != b.getPixelAt (x, y))
                return false;
    return true;
}

void hearEngine (DeskComponent& desk, const char* key, int number, int value, double t)
{
    desk.receive (juce::OSCMessage (juce::OSCAddressPattern (osc().address (key, number)), value), t);
}
}

// The return display is the same before and after Core's first source report, and after a new Core takes the
// desk out of engine mode (the display is the fifth OledView, after the four channels).
TEST (DeskRing, TheReturnDisplayIsTheSameInEveryMode)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->step (140);
    const auto reaper = displayShot (*desk, 4);
    hearEngine (*desk, "channel.source", 1, 1, 200);
    desk->step (220);
    EXPECT_TRUE (samePixels (reaper, displayShot (*desk, 4)));

    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-2" }, 9000);
    desk->step (9020);
    answer (*desk, 9100);
    desk->step (9120);
    EXPECT_TRUE (samePixels (reaper, displayShot (*desk, 4)));
}

// Without Core's source reports (REAPER mode) the display is the interim's, whatever else arrives; a new
// Core takes the desk out of engine mode again.
// Five fixed slots (maintainer, 2026-10-28): the truth has the engine's words, so the ring A B C D ST with
// analog playing is the first picture, and a new Core brings that picture back -- never the interim's.
TEST (DeskRing, TheRingFromTheStartAndAfterANewCore)
{
    Captured c;
    auto desk = deskJoined (c);
    desk->step (140);
    const auto start = displayShot (*desk, 0);
    hearEngine (*desk, "channel.source", 1, 0, 160);   // Core's first report: analog, as already shown
    desk->step (180);
    EXPECT_TRUE (samePixels (start, displayShot (*desk, 0)));

    hearEngine (*desk, "channel.source", 1, 1, 200);
    desk->step (220);
    EXPECT_FALSE (samePixels (start, displayShot (*desk, 0)));

    desk->announced ({ "http://core/a3-osc.json", test::truth().digest(), "boot-2" }, 9000);
    desk->step (9020);
    answer (*desk, 9100);   // the surface dims until the new Core answers
    desk->step (9120);
    EXPECT_TRUE (samePixels (start, displayShot (*desk, 0)));
}

namespace
{
/** SELECT, the FX Return's encoder: after the four channels' INPUT encoders. */
DeskEncoder* selectOf (DeskComponent& desk) { return nthChild<DeskEncoder> (desk, numChannels); }

void turnBy (DeskEncoder& encoder, int clicks)
{
    const juce::Point<float> at { encoder.getWidth() * 0.5f, encoder.getHeight() * 0.5f };
    for (int i = 0; i < std::abs (clicks); ++i)
        encoder.mouseWheelMove (clickOn (encoder, at, at, false),
                                juce::MouseWheelDetails { 0.f, clicks > 0 ? 0.1f : -0.1f, false, false, false });
}

void push (DeskEncoder& encoder)
{
    const juce::Point<float> at { encoder.getWidth() * 0.5f, encoder.getHeight() * 0.5f };
    encoder.mouseDown (clickOn (encoder, at, at, false));
    encoder.mouseUp (clickOn (encoder, at, at, false));
}

DeskLayout layoutOf (DeskComponent& desk) { return layOutDesk (desk.getLocalBounds().toFloat(), currentFingertip()); }
}

// The hardware's return encoder (a3_mixer_delay): selecting, a turn moves the cursor and sends nothing; a
// press is edit, and a turn then sends the row's turn word with the clicks; another press selects again.
TEST (DeskComponent, TheReturnEncoderWalksTheDelayListAsTheHardware)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* select = selectOf (*desk);
    ASSERT_NE (select, nullptr);
    turnBy (*select, -1);   // left: BEAT -> FEEDBK, down the list
    push (*select);
    EXPECT_TRUE (c.sent.empty()) << c.addresses().joinIntoString (" ");
    turnBy (*select, 1);
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("aux-return.delay.feedback.turn"));
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 1);
    push (*select);   // select again: the turn moves the cursor
    c.sent.clear();
    turnBy (*select, -1);
    EXPECT_TRUE (c.sent.empty());
    push (*select);
    turnBy (*select, -1);
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("aux-return.delay.color.turn"));
    EXPECT_EQ (c.sent[0].message[0].getInt32(), -1);
}

// R22: four quiet seconds in edit and the encoder selects again.
TEST (DeskComponent, TheDelayListFallsBackToSelect)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* select = selectOf (*desk);
    push (*select);
    desk->step (100 + delay::fallbackMs + 50);
    c.sent.clear();
    turnBy (*select, 1);
    EXPECT_TRUE (c.sent.empty());
}

// The return display shows Core's values and the mode: a press and Core's value change its pixels.
TEST (DeskComponent, TheReturnDisplayShowsTheModeAndCoresValues)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* display = nthChild<OledView> (*desk, numChannels);
    ASSERT_NE (display, nullptr);
    desk->step (140);
    const auto selecting = display->createComponentSnapshot (display->getLocalBounds());
    push (*selectOf (*desk));
    desk->step (180);
    const auto editing = display->createComponentSnapshot (display->getLocalBounds());
    desk->receive (juce::OSCMessage (juce::OSCAddressPattern (osc().address ("aux-return.delay.beat")), 0.5f), 190);
    desk->step (220);
    const auto valued = display->createComponentSnapshot (display->getLocalBounds());
    const auto differ = [] (const juce::Image& a, const juce::Image& b) {
        for (int y = 0; y < a.getHeight(); ++y)
            for (int x = 0; x < a.getWidth(); ++x)
                if (a.getPixelAt (x, y) != b.getPixelAt (x, y))
                    return true;
        return false;
    };
    EXPECT_TRUE (differ (selecting, editing));
    EXPECT_TRUE (differ (editing, valued));
}

// Maintainer, 2026-10-30: of the four tap keys only the fourth is TAP; the third is DELAY CUE.
TEST (DeskComponent, TheThirdTapKeyIsDelayCueAndTheFourthTap)
{
    Captured c;
    auto desk = deskJoined (c);
    const auto layout = layoutOf (*desk);
    auto* tap = desk->controlFor ("tap", 0);
    auto* cue = dynamic_cast<DeskKey*> (desk->controlFor ("aux-return.stem.push", 0));
    ASSERT_NE (tap, nullptr);
    ASSERT_NE (cue, nullptr);
    EXPECT_EQ (tap->getBounds(), layout.strips[3].tap.toNearestInt());
    EXPECT_EQ (cue->getBounds(), layout.strips[2].tap.toNearestInt());
    for (size_t strip : { 0u, 1u })
        for (auto* child : desk->getChildren())
            EXPECT_FALSE (child->getBounds().intersects (layout.strips[strip].tap.toNearestInt()))
                << "strip " << strip + 1 << ": " << child->getBounds().toString();

    // The cue is a toggle at Core: a press sends it, the release nothing (as the hardware's push).
    cue->mouseDown (clickOn (*cue, { 2.f, 2.f }, { 2.f, 2.f }, false));
    cue->mouseUp (clickOn (*cue, { 2.f, 2.f }, { 2.f, 2.f }, false));
    ASSERT_EQ (c.sent.size(), 1u);
    EXPECT_EQ (c.sent[0].message.getAddressPattern().toString(), osc().address ("aux-return.stem.push"));
    EXPECT_EQ (c.sent[0].message[0].getInt32(), 1);
}

TEST (DeskComponent, DelayCueIsLitByCoresLamp)
{
    Captured c;
    auto desk = deskJoined (c);
    auto* cue = desk->controlFor ("aux-return.stem.push", 0);
    desk->step (140);
    const auto off = cue->createComponentSnapshot (cue->getLocalBounds());
    desk->receive (juce::OSCMessage (juce::OSCAddressPattern (osc().address ("aux-return.cue.led")), 1.f), 150);
    desk->step (180);
    const auto on = cue->createComponentSnapshot (cue->getLocalBounds());
    int differing = 0;
    for (int y = 0; y < on.getHeight(); ++y)
        for (int x = 0; x < on.getWidth(); ++x)
            differing += on.getPixelAt (x, y) != off.getPixelAt (x, y) ? 1 : 0;
    EXPECT_GT (differing, on.getWidth() * on.getHeight() / 4);
}

// Maintainer, 2026-10-30: LOCK is gone; the keys are one TAP, DELAY CUE, four FX, four CUE, HPF and LPF.
TEST (DeskComponent, ThereIsNoLock)
{
    Captured c;
    auto desk = deskJoined (c);
    int keys = 0;
    for (auto* child : desk->getChildren())
        keys += dynamic_cast<DeskKey*> (child) != nullptr ? 1 : 0;
    EXPECT_EQ (keys, 2 + 2 * numChannels + 2);
    desk->touchPot (potIndex ("master.volume", 0), 0.2f);
    EXPECT_EQ (c.sent.size(), 1u);
}

// Larger knobs in the master column, not larger captions: every pot's caption is a strip pot's.
TEST (DeskComponent, EveryMasterPotHasTheStripsCaptionSize)
{
    Captured c;
    auto desk = deskJoined (c);
    const auto layout = layoutOf (*desk);
    const float strip = layout.strips[0].pots[0].getHeight() * DeskLook::captionOfCell;
    for (const auto& key : masterPotKeys)
    {
        auto* knob = dynamic_cast<DeskKnob*> (desk->controlFor (key, 0));
        ASSERT_NE (knob, nullptr) << key;
        ASSERT_TRUE (knob->captionHeight.has_value()) << key;
        EXPECT_FLOAT_EQ (*knob->captionHeight, strip) << key;
    }
}

// Maintainer, 2026-10-30: MASTER and BOOTH at the very top of the master column, above the output VU.
TEST (DeskComponent, MasterAndBoothStandAboveTheOutputMeters)
{
    Captured c;
    auto desk = deskJoined (c);
    const auto layout = layoutOf (*desk);
    for (const auto* key : { "master.volume", "master.booth" })
    {
        auto* knob = desk->controlFor (key, 0);
        ASSERT_NE (knob, nullptr);
        EXPECT_LT (knob->getBottom(), layout.matrix.getY() + 1) << key;
        EXPECT_TRUE (layout.outputCard.toNearestInt().contains (knob->getBounds())) << key;
    }
}

namespace
{
/** One finger dragging up `rise` pixels on the rig: touch#0 and X's emulated mouse#0 each go down, move in
    steps -- the mouse a step behind, as X's copy lags -- and lift; Core relays `relayed` (of the desk's
    current value) after every step, as it relays the pot to every desk. */
void dragTwiceDelivered (DeskComponent& desk, juce::ComponentPeer& peer, int pot, juce::Point<float> at, float rise,
                         juce::int64 t, const std::function<float (float)>& relayed)
{
    constexpr int steps = 10;
    const auto move = [&peer] (Source s, juce::Point<float> p, juce::int64 ms) {
        peer.handleMouseEvent (s, p, juce::ModifierKeys (juce::ModifierKeys::leftButtonModifier), 1.f, 0.f, ms);
    };
    press (peer, Source::touch, at, t);
    press (peer, Source::mouse, at, t + 2);
    auto last = at;
    for (int i = 1; i <= steps; ++i)
    {
        const auto p = at.translated (0.f, -rise * static_cast<float> (i) / steps);
        move (Source::touch, p, t + 10 * i);
        move (Source::mouse, last, t + 10 * i + 2);
        last = p;
        const auto& k = allPots()[(size_t) pot];
        desk.receive (juce::OSCMessage (juce::OSCAddressPattern (osc().address (k.key, k.channel)), relayed (desk.state().value (pot))),
                      (double) (t + 10 * i + 5));
    }
    lift (peer, Source::touch, last, t + 200);
    lift (peer, Source::mouse, last, t + 202);
}
}

// Maintainer, 2026-10-30, on the rig: "I can't operate the pots". A finger's drag, delivered twice as the
// rig's X delivers it, moves the pot with the finger and sends the new value -- every kind of pot.
TEST (DeskComponent, AFingerDragsAPotOnTheRig)
{
    for (const auto& [key, channel] : std::vector<std::pair<std::string, int>> {
             { "channel.gain", 1 }, { "channel.eq.mid", 3 }, { "master.volume", 0 }, { "filter.frequency", 0 } })
    {
        Captured c;
        auto desk = deskJoined (c);
        desk->setSize (768, 1024);
        test::PeerHost window;
        window.setBounds (desk->getLocalBounds());
        window.addAndMakeVisible (*desk);
        window.addToDesktop (0);
        window.setVisible (true);
        auto* peer = window.getPeer();
        ASSERT_NE (peer, nullptr);
        const int pot = potIndex (key, channel);
        const auto& k = allPots()[(size_t) pot];
        desk->receive (juce::OSCMessage (juce::OSCAddressPattern (osc().address (k.key, k.channel)), 0.3f), 500);   // Core's value
        c.sent.clear();
        auto* control = potControl (*desk, pot);
        const auto at = control->getBounds().getCentre().toFloat();
        const float rise = 0.25f * static_cast<float> (control->getHeight());

        dragTwiceDelivered (*desk, *peer, pot, at, rise, 10000, [] (float sent) { return sent; });
        ASSERT_FALSE (c.sent.empty()) << key;
        const float expected = juce::jmin (1.f, 0.3f + rise / (4.f * static_cast<float> (control->getHeight())));
        EXPECT_NEAR (c.sent.back().message[0].getFloat32(), expected, 0.02f) << key;
        EXPECT_NEAR (desk->state().value (pot), expected, 0.02f) << key;
        EXPECT_NEAR ((float) control->getValue(), expected, 0.02f) << key;
        // Values only rise with the finger: X's lagging copy never pulls the pot back.
        for (size_t i = 1; i < c.sent.size(); ++i)
            EXPECT_GE (c.sent[i].message[0].getFloat32() + 1e-6f, c.sent[i - 1].message[0].getFloat32()) << key << " " << i;
        window.removeChildComponent (desk.get());
    }
}
