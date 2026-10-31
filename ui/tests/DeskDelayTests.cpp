// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskDelay.h"
#include "TestTruth.h"

using namespace desk::delay;

// The hardware's return encoder (a3_mixer_delay.DelayList): select is the start mode with the cursor on
// BEAT, a turn moves the cursor and stops at the ends -- left down the list, right up (maintainer,
// 2026-10-30); a press toggles select and edit.
TEST (DeskDelay, SelectMovesTheCursorAndStopsAtTheEnds)
{
    DelayList list;
    EXPECT_EQ (list.mode(), Mode::select);
    EXPECT_EQ (list.cursor(), 0);
    EXPECT_FALSE (list.turn (1, 0.0));
    EXPECT_EQ (list.cursor(), 0);
    EXPECT_FALSE (list.turn (-2, 0.0));
    EXPECT_EQ (list.cursor(), 2);
    EXPECT_FALSE (list.turn (-5, 0.0));
    EXPECT_EQ (list.cursor(), rowCount - 1);   // SPREAD: CUE is no row on the desk
    EXPECT_FALSE (list.turn (1, 0.0));
    EXPECT_EQ (list.cursor(), 2);
}

// The same cursor as the hardware's after the same turns, through the shared fixture.
TEST (DeskDelay, TheCursorMovesAsThePythons)
{
    const auto* cases = desk::test::fixture()["delay_cursor"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_GE (cases->size(), 5);
    for (const auto& c : *cases)
    {
        DelayList list;
        juce::String turns;
        for (const auto& clicks : *c["turns"].getArray())
        {
            list.turn ((int) clicks, 0.0);
            turns << (int) clicks << " ";
        }
        EXPECT_EQ (list.cursor(), (int) c["cursor"]) << turns;
    }
}

TEST (DeskDelay, EditTurnsTheRowUnderTheCursor)
{
    DelayList list;
    list.turn (-1, 0.0);
    list.press (0.0);
    EXPECT_EQ (list.mode(), Mode::edit);
    const auto row = list.turn (-3, 100.0);   // edit: the clicks as they are, right = more
    ASSERT_TRUE (row.has_value());
    EXPECT_EQ (*row, 1);
    EXPECT_EQ (list.cursor(), 1);   // edit never moves the cursor
    EXPECT_FALSE (list.turn (0, 100.0));
    list.press (200.0);
    EXPECT_EQ (list.mode(), Mode::select);
}

// R22: four quiet seconds in edit and the encoder selects again, the cursor staying; a turn starts them over.
TEST (DeskDelay, EditFallsBackToSelectAfterFourQuietSeconds)
{
    DelayList list;
    list.turn (-2, 0.0);
    list.press (0.0);
    list.step (fallbackMs - 1.0);
    EXPECT_EQ (list.mode(), Mode::edit);
    list.turn (1, 3000.0);
    list.step (3000.0 + fallbackMs - 1.0);
    EXPECT_EQ (list.mode(), Mode::edit);
    list.step (3000.0 + fallbackMs);
    EXPECT_EQ (list.mode(), Mode::select);
    EXPECT_EQ (list.cursor(), 2);
}

TEST (DeskDelay, SelectHasNoFallback)
{
    DelayList list;
    list.turn (-3, 0.0);
    list.step (10.0 * fallbackMs);
    EXPECT_EQ (list.mode(), Mode::select);
    EXPECT_EQ (list.cursor(), 3);
}

TEST (DeskDelay, TheRowsAreTheHardwaresWithoutCue)
{
    EXPECT_EQ (rowCount, 4);
    EXPECT_STREQ (rowName (0), "BEAT");
    EXPECT_STREQ (rowName (1), "FEEDBK");
    EXPECT_STREQ (rowName (2), "COLOR");
    EXPECT_STREQ (rowName (3), "SPREAD");
    EXPECT_EQ (turnKey (2), "aux-return.delay.color.turn");
    EXPECT_EQ (valueKey (3), "aux-return.delay.spread");
    EXPECT_EQ (rowOfValueKey ("aux-return.delay.feedback"), 1);
    EXPECT_FALSE (rowOfValueKey ("aux-return.delay.feedback.turn").has_value());
}

// The hardware's texts (display_panel.delay_text), through the shared fixture.
TEST (DeskDelay, ValueTextsAreThePythons)
{
    const auto* cases = desk::test::fixture()["delay_texts"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_GT (cases->size(), 20);
    for (const auto& c : *cases)
    {
        const auto row = rowOfName (c["row"].toString().toStdString());
        ASSERT_TRUE (row.has_value()) << c["row"].toString();
        const auto value = c["value"].isVoid() ? std::nullopt : std::optional<double> ((double) c["value"]);
        EXPECT_EQ (juce::String::fromUTF8 (valueText (*row, value).c_str()), c["text"].toString())
            << c["row"].toString() << " " << c["value"].toString();
    }
}

// The same keys as the hardware's a3_mixer_osc.DELAY_KEYS: optional, all or nothing.
TEST (DeskDelay, TheKeysAreThePythons)
{
    const auto* keys = desk::test::fixture()["tables"]["delay_keys"].getArray();
    ASSERT_NE (keys, nullptr);
    std::vector<std::string> python;
    for (const auto& k : *keys)
        python.push_back (k.toString().toStdString());
    EXPECT_EQ (python, delayKeys());
}
