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
    ASSERT_EQ (cases->size(), 45);
    for (const auto& c : *cases)
    {
        const auto picture = channelPicture (c["cursor"], arrayOf<9, double> (c["levels"]), c["mask"],
                                             c["width"], c["height"], arrayOf<9, bool> (c["clips"]),
                                             arrayOf<9, double> (c["holds"]));
        expectSamePicture (picture, c["picture"], "cursor " + c["cursor"].toString() + " mask " + c["mask"].toString());
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
    const auto picture = channelPicture (0, { 1, 0, 0, 0, 0, 0, 0, 0, 0 }, 1, oledWidth, oledHeight,
                                         { true, false, false, false, false, false, false, false, false }, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
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
    const auto picture = channelPicture (8, {}, 0, oledWidth, oledHeight, {}, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    const auto& a = picture.cursor;
    EXPECT_GT (image.getPixelAt (a.x0, a.y0).getBrightness(), 0.5f);              // top row full width
    EXPECT_LT (image.getPixelAt (a.x0, a.y1).getBrightness(), 0.5f);              // narrower below
}
