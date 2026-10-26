// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DisplayPaint.h"
#include "DisplayPicture.h"
#include "TestTruth.h"

using namespace desk::display;

namespace
{
juce::var boxVar (const Box& b) { return juce::Array<juce::var> { b.x0, b.y0, b.x1, b.y1 }; }

juce::var asVar (const Picture& p, const char* field)
{
    const juce::String f (field);
    juce::Array<juce::var> out;
    if (f == "headings")
        for (const auto& h : p.headings) out.add (juce::Array<juce::var> { h.box.x0, h.box.y0, h.box.x1, h.box.y1, juce::String (h.text) });
    if (f == "meters")
        for (const auto& m : p.meters)
            out.add (juce::Array<juce::var> { m.box.x0, m.box.y0, m.box.x1, m.box.y1, m.pixels(), m.hatched(), m.holdRow().value_or (-1) });
    if (f == "dividers") for (const auto& d : p.dividers) out.add (boxVar (d));
    if (f == "marks") for (const auto& m : p.marks) out.add (boxVar (m));
    if (f == "cursor") return boxVar (p.cursor);
    if (f == "active") return boxVar (p.active);
    if (f == "toggle")
        return p.toggle ? juce::var (juce::Array<juce::var> { p.toggle->box.x0, p.toggle->box.y0, p.toggle->box.x1,
                                                              p.toggle->box.y1, p.toggle->on, juce::String (p.toggle->text) })
                        : juce::var();
    return out;
}

void expectSamePicture (const Picture& got, const juce::var& expected, const juce::String& which)
{
    for (const auto* field : { "headings", "meters", "cursor", "dividers", "toggle", "active", "marks" })
        EXPECT_EQ (juce::JSON::toString (asVar (got, field), true),
                   juce::JSON::toString (expected[juce::Identifier (field)], true)) << which << " " << field;
}

template <size_t N, typename T>
std::array<T, N> arrayOf (const juce::var& v)
{
    std::array<T, N> out {};
    for (size_t i = 0; i < N; ++i)
        out[i] = static_cast<T> (v[static_cast<int> (i)]);
    return out;
}
}

TEST (DisplayPicture, ChannelPicturesAreThePythons)
{
    const auto* cases = desk::test::fixture()["channel_pictures"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_EQ (cases->size(), 80);
    for (const auto& c : *cases)
    {
        const auto picture = channelPicture (c["channel"], c["cursor"], arrayOf<3, double> (c["levels"]), c["mask"],
                                             c["width"], c["height"], arrayOf<3, bool> (c["clips"]),
                                             arrayOf<3, double> (c["holds"]));
        expectSamePicture (picture, c["picture"],
                           "channel " + c["channel"].toString() + " cursor " + c["cursor"].toString()
                               + " mask " + c["mask"].toString());
    }
}

TEST (DisplayPicture, ReturnPicturesAreThePythons)
{
    const auto* cases = desk::test::fixture()["return_pictures"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_EQ (cases->size(), 12);
    for (const auto& c : *cases)
    {
        const auto picture = returnPicture (c["cursor"], c["mode"], c["cue"], arrayOf<2, double> (c["levels"]),
                                            c["width"], c["height"], arrayOf<2, bool> (c["clips"]),
                                            arrayOf<2, double> (c["holds"]));
        expectSamePicture (picture, c["picture"], "return " + c["cursor"].toString() + "/" + c["mode"].toString());
    }
}

TEST (ClipHold, AnOverLightsItForOneSecond)
{
    ClipHold hold;
    EXPECT_FALSE (hold.feed (0.9f, 0.1));
    EXPECT_TRUE (hold.feed (1.2f, 0.1));
    for (int i = 0; i < 9; ++i)
        EXPECT_TRUE (hold.feed (0.5f, 0.1)) << i;
    EXPECT_FALSE (hold.feed (0.5f, 0.1));
}

TEST (DisplayPaint, PaintsTheBarWhiteAndTheHatchDark)
{
    const auto picture = channelPicture (0, 0, { 1, 0, 0 }, 1, oledWidth, oledHeight, { true, false, false }, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    ASSERT_EQ (picture.meters.size(), 3u);   // an empty picture must fail, not crash the runner
    const auto& bar = picture.meters[0].box;
    int white = 0, dark = 0;
    for (int x = bar.x0; x <= bar.x1; ++x)
        for (int y = bar.y0; y <= bar.y1; ++y)
            (image.getPixelAt (x, y).getBrightness() > 0.5f ? white : dark)++;
    EXPECT_GT (white, dark);   // a hatched bar is still mostly a bar
    EXPECT_GT (dark, 0);       // ... and plainly not a solid one
}

TEST (DisplayPaint, TheArrowPointsDownAtTheCursor)
{
    const auto picture = channelPicture (0, 8, {}, 0, oledWidth, oledHeight, {}, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    const auto& a = picture.cursor;
    EXPECT_GT (image.getPixelAt (a.x0, a.y0).getBrightness(), 0.5f);              // top row full width
    EXPECT_LT (image.getPixelAt (a.x0, a.y1).getBrightness(), 0.5f);              // narrower below
    ASSERT_EQ (picture.meters.size(), 3u);
    const auto& analog = picture.meters[2].box;                                    // a cursor of 8 is A
    EXPECT_LE (std::abs ((a.x0 + a.x1) - (analog.x0 + analog.x1)), 1);
}

// The engine-mode ring is the Python desk's, case for case (every source, cursor and presence).
TEST (DisplayPicture, DeckChannelSnapshot)
{
    const auto* cases = desk::test::fixture()["engine_channel_pictures"].getArray();
    ASSERT_NE (cases, nullptr);
    ASSERT_EQ (cases->size(), 36);
    for (const auto& c : *cases)
    {
        const auto picture = enginePicture (c["source"], c["cursor"],
                                            { static_cast<bool> (c["present"][0]), static_cast<bool> (c["present"][1]) },
                                            arrayOf<3, double> (c["levels"]), c["width"], c["height"],
                                            arrayOf<3, bool> (c["clips"]), arrayOf<3, double> (c["holds"]));
        expectSamePicture (picture, c["picture"], "source " + c["source"].toString() + " cursor " + c["cursor"].toString()
                                                      + " present " + juce::JSON::toString (c["present"], true));
    }
}

// A page test must paint: an absent deck is a dash over an empty slot, a present one a bar.
TEST (DisplayPicture, DeckChannelSnapshotPaintsAbsentDeckEmpty)
{
    const auto picture = enginePicture (0, 0, { true, false }, { 1, 1, 1 }, oledWidth, oledHeight, {}, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    ASSERT_EQ (picture.meters.size(), 3u);
    const auto lit = [&] (const Box& b) {
        int n = 0;
        for (int x = b.x0; x <= b.x1; ++x)
            for (int y = b.y0; y <= b.y1; ++y)
                n += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
        return n;
    };
    EXPECT_GT (lit (picture.meters[0].box), 0);   // AN
    EXPECT_GT (lit (picture.meters[1].box), 0);   // deck A
    EXPECT_EQ (lit (picture.meters[2].box), 0);   // deck B absent: no bar
    EXPECT_EQ (picture.headings[2].text, "-");
}

TEST (DeskRing, EngineModeLabelsOnThePicture)
{
    const auto both = enginePicture (1, 2, { true, true }, {}, oledWidth, oledHeight, {}, {});
    ASSERT_EQ (both.headings.size(), 3u);
    EXPECT_EQ (both.headings[0].text, "AN");
    EXPECT_EQ (both.headings[1].text, "A");
    EXPECT_EQ (both.headings[2].text, "B");
    const auto centre = [] (const Box& b) { return b.x0 + b.x1; };
    EXPECT_LE (std::abs (centre (both.cursor) - centre (both.meters[2].box)), 1);   // arrow over B
    EXPECT_EQ (both.active.x0, both.meters[1].box.x0 - 1);                          // bracket round A
    // An absent deck keeps cursor and bracket (they are Core's) and is only drawn "-".
    const auto absent = enginePicture (2, 2, { true, false }, {}, oledWidth, oledHeight, {}, {});
    EXPECT_EQ (absent.headings[2].text, "-");
    EXPECT_EQ (absent.active.x0, absent.meters[2].box.x0 - 1);
    EXPECT_LE (std::abs (centre (absent.cursor) - centre (absent.meters[2].box)), 1);
}

// Core's decks C and D (3, 4): the ring is AN | A | B, so a channel on one shows the letter alone;
// a cursor on one selects no ring slot (no arrow). Nothing indexes past the ring.
TEST (DeskRing, AChannelOnDeckCOrDShowsThatLetter)
{
    for (const auto [source, letter] : { std::pair { 3, "C" }, std::pair { 4, "D" } })
    {
        const auto p = enginePicture (source, 0, { true, true }, {}, oledWidth, oledHeight, {}, {});
        ASSERT_EQ (p.headings.size(), 1u);
        EXPECT_EQ (p.headings[0].text, letter);
        EXPECT_TRUE (p.meters.empty());
        EXPECT_LT (p.active.x1, p.active.x0);   // no bracket
        EXPECT_LT (p.cursor.y1, p.cursor.y0);   // no arrow
        const auto image = paintPicture (p, oledWidth, oledHeight);
        int lit = 0;
        for (int x = 0; x < oledWidth; ++x)
            for (int y = 0; y < oledHeight; ++y)
                lit += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
        EXPECT_GT (lit, 40);                    // the letter is drawn, and nothing else
    }
}

TEST (DeskRing, ACursorOnDeckCOrDSelectsNoRingSlot)
{
    for (const int cursor : { 3, 4 })
    {
        const auto p = enginePicture (1, cursor, { true, true }, {}, oledWidth, oledHeight, {}, {});
        ASSERT_EQ (p.headings.size(), 3u);
        EXPECT_LT (p.cursor.y1, p.cursor.y0);
        EXPECT_EQ (p.active.x0, p.meters[1].box.x0 - 1);   // the bracket is Core's source, kept
    }
}
