// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskControls.h"
#include "DeskWire.h"
#include "StartupAsk.h"
#include "TestTruth.h"

using namespace desk;

namespace
{
const DeskOsc& osc()
{
    static const DeskOsc made (test::truth());
    return made;
}
}

// D5: keys, turns and tap as the hardware sends them. Pots are float32 by plan
// change #3 (the hardware sends strings; Core floats them either way and relays
// a float) -- do not "fix" them back to strings. Keys are the panel's text edges -- a3_core_buttons tells a
// press ("1") from a screen's state (a number) by the type.
TEST (DeskWire, PotsTravelAsFloat32)
{
    const DeskWire wire (osc());
    const auto out = wire.pot (potIndex ("channel.gain", 3), 0.25f);
    EXPECT_EQ (out.to, Outgoing::To::core);
    EXPECT_EQ (out.message.getAddressPattern().toString(), osc().address ("channel.gain", 3));
    ASSERT_TRUE (out.message[0].isFloat32());
    EXPECT_FLOAT_EQ (out.message[0].getFloat32(), 0.25f);
}

TEST (DeskWire, KeysTravelAsTextEdges)
{
    const DeskWire wire (osc());
    const auto press = wire.key ("channel.cue", 2, true);
    const auto release = wire.key ("channel.cue", 2, false);
    EXPECT_EQ (press.message.getAddressPattern().toString(), osc().address ("channel.cue", 2));
    ASSERT_TRUE (press.message[0].isString());
    EXPECT_EQ (press.message[0].getString(), "1");
    EXPECT_EQ (release.message[0].getString(), "0");
}

TEST (DeskWire, HpfAndLpfSendTheWord)
{
    const DeskWire wire (osc());
    EXPECT_EQ (wire.filterMode (true).message[0].getString(), "high_pass");
    EXPECT_EQ (wire.filterMode (false).message[0].getString(), "low_pass");
    EXPECT_EQ (wire.filterMode (true).message.getAddressPattern().toString(), osc().address ("filter.mode"));
}

TEST (DeskWire, TurnsAndPushesAreInt32)
{
    const DeskWire wire (osc());
    const auto turn = wire.channelTurn (4, -2);
    EXPECT_EQ (turn.message.getAddressPattern().toString(), osc().address ("channel.stem.turn", 4));
    EXPECT_EQ (turn.message[0].getInt32(), -2);
    EXPECT_TRUE (turn.message[0].isInt32());
    EXPECT_EQ (wire.returnTurn (1).message[0].getInt32(), 1);
    EXPECT_TRUE (wire.returnTurn (1).message[0].isInt32());
    EXPECT_EQ (wire.returnTurn (1).message.getAddressPattern().toString(), osc().address ("aux-return.stem.turn"));
    EXPECT_EQ (wire.channelPush (1).message[0].getInt32(), 1);
    EXPECT_TRUE (wire.channelPush (1).message[0].isInt32());
    EXPECT_TRUE (wire.returnPush().message[0].isInt32());
    EXPECT_EQ (wire.returnPush().message.getAddressPattern().toString(), osc().address ("aux-return.stem.push"));
}

TEST (DeskWire, TapGoesToTheBeatClockAsInt1)
{
    const auto tap = DeskWire (osc()).tap();
    EXPECT_EQ (tap.to, Outgoing::To::beatClock);
    EXPECT_EQ (tap.message[0].getInt32(), 1);
    EXPECT_TRUE (tap.message[0].isInt32());
    EXPECT_EQ (tap.message.getAddressPattern().toString(), osc().address ("tap"));
}

TEST (DeskWire, HelloNamesTheDeskAndItsTruth)
{
    const auto hello = DeskWire (osc()).hello ("abc");
    EXPECT_EQ (hello.message.getAddressPattern().toString(), osc().address ("device.hello"));
    EXPECT_EQ (hello.message[0].getString(), "desk");
    EXPECT_EQ (hello.message[1].getString(), "abc");
}

TEST (StartupAsk, AtStartHelloAndRecallOnly)
{
    StartupAsk ask;
    EXPECT_EQ (ask.due (0, true), (std::vector<StartupAsk::Send> { StartupAsk::Send::hello, StartupAsk::Send::recall }));
}

TEST (StartupAsk, AStaleTruthNeverAsksForRecall)
{
    // Same gate as the hello: a desk whose truth is not Core's would flood Core
    // with replays every 5 s for two minutes.
    StartupAsk ask;
    for (double t = 0; t <= 130000; t += 5000)
        EXPECT_TRUE (ask.due (t, false).empty());
}

TEST (StartupAsk, AskingStartsOnlyOnceTheTruthIsCores)
{
    // A stale hello would close this host in Core's gate -- for the Motion beside it too.
    StartupAsk ask;
    EXPECT_TRUE (ask.due (0, false).empty());
    EXPECT_EQ (ask.due (1000, true), (std::vector<StartupAsk::Send> { StartupAsk::Send::hello, StartupAsk::Send::recall }));
}

TEST (StartupAsk, RecallEveryFiveSecondsUntilAnswered)
{
    StartupAsk ask;
    ask.due (0, true);
    EXPECT_TRUE (ask.due (4999, true).empty());
    EXPECT_EQ (ask.due (5000, true), std::vector<StartupAsk::Send> { StartupAsk::Send::recall });
    ask.answered();
    EXPECT_TRUE (ask.due (20000, true).empty());
    EXPECT_EQ (ask.due (30000, true), std::vector<StartupAsk::Send> { StartupAsk::Send::hello });
}

TEST (StartupAsk, GivesUpAfterTwoMinutes)
{
    StartupAsk ask;
    for (double t = 0; t <= 120000; t += 5000)
        ask.due (t, true);
    EXPECT_TRUE (ask.gaveUp (120001));
    for (const auto s : ask.due (125000, true))
        EXPECT_NE (s, StartupAsk::Send::recall);
}

// Review focus 2.
TEST (StartupAsk, NoHandsBeforeCoreAnswers)
{
    StartupAsk ask;
    ask.due (0, true);
    EXPECT_FALSE (ask.joined());
    ask.answered();
    EXPECT_TRUE (ask.joined());
}

// Review focus 3: never a dump of positions -- only hello and recall exist here.
TEST (StartupAsk, ANewBootIdAsksAgainAndSendsNoValue)
{
    StartupAsk ask;
    CoreWatch core;
    EXPECT_FALSE (core.heard ("f", "boot-1", 0));
    ask.due (0, true);
    ask.answered();
    EXPECT_TRUE (core.heard ("f", "boot-2", 9000));
    ask.coreRestarted (9000);
    EXPECT_FALSE (ask.joined());
    EXPECT_EQ (ask.due (9000, true), (std::vector<StartupAsk::Send> { StartupAsk::Send::hello, StartupAsk::Send::recall }));
}

TEST (CoreWatch, FiveSecondsWithoutAnnouncementIsSilence)
{
    CoreWatch core;
    EXPECT_TRUE (core.silent (0));
    core.heard ("f", "b", 1000);
    EXPECT_FALSE (core.silent (6000));
    EXPECT_TRUE (core.silent (6001));
    EXPECT_EQ (core.fingerprint(), "f");
}

TEST (CoreWatch, AnOlderCoreWithoutBootIdIsNeverANewOne)
{
    CoreWatch core;
    core.heard ("f", {}, 0);
    EXPECT_FALSE (core.heard ("f", {}, 2000));
}

// Final review I1: a Core heard again after silence (a link drop, same boot id)
// has lost every relay sent meanwhile, and may have dropped the desk -- ask again.
TEST (CoreWatch, BackFromSilenceIsAskedAgain)
{
    CoreWatch core;
    EXPECT_FALSE (core.heard ("f", "boot-1", 0));
    EXPECT_FALSE (core.heard ("f", "boot-1", 5000));    // 5 s exactly is not yet silence
    EXPECT_TRUE (core.heard ("f", "boot-1", 10001));
    EXPECT_FALSE (core.heard ("f", "boot-1", 12000));
}

TEST (DeskWire, RecallGoesToCoreAsInt1)
{
    const auto recall = DeskWire (osc()).recall();
    EXPECT_EQ (recall.to, Outgoing::To::core);
    EXPECT_EQ (recall.message.getAddressPattern().toString(), osc().address ("state.recall"));
    ASSERT_TRUE (recall.message[0].isInt32());
    EXPECT_EQ (recall.message[0].getInt32(), 1);
}

TEST (StartupAsk, ARestartDuringAStaleTruthDoesNotBurnTheRecallWindow)
{
    StartupAsk ask;
    ask.due (0, true);
    ask.answered();
    ask.coreRestarted (9000);
    EXPECT_TRUE (ask.due (200000, false).empty());
    EXPECT_FALSE (ask.gaveUp (200000));
    EXPECT_EQ (ask.due (200000, true), (std::vector<StartupAsk::Send> { StartupAsk::Send::hello, StartupAsk::Send::recall }));
}

TEST (StartupAsk, JoinedThenAStaleTruthSaysNoHello)
{
    StartupAsk ask;
    ask.due (0, true);
    ask.answered();
    EXPECT_TRUE (ask.due (30000, false).empty());
}
