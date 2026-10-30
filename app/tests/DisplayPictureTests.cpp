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
// An empty box (none) is Python's None.
juce::var boxVar (const Box& b)
{
    if (isEmpty (b))
        return {};
    return juce::Array<juce::var> { b.x0, b.y0, b.x1, b.y1 };
}

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
    ASSERT_EQ (cases->size(), 2);
    for (const auto& c : *cases)
    {
        const auto picture = returnPicture (c["cue"], c["level"], c["width"], c["height"], c["clip"], c["hold"]);
        expectSamePicture (picture, c["picture"], "return cue " + c["cue"].toString());
    }
}

// P47: the FX Return is the delay channel's master: one meter under DELAY, the CUE
// field, no arrow and no bracket. The name's box is what DELAY needs; the meter stands where it stood
// under FX RTN (columns 39-60).
TEST (DisplayPicture, TheReturnIsOneMeterNamedAuxRtn)
{
    const auto picture = returnPicture (false, 0.5, 128, 64, false, 0.0);
    ASSERT_EQ (picture.headings.size(), 1u);
    EXPECT_EQ (picture.headings[0].text, "DELAY");
    ASSERT_EQ (picture.meters.size(), 1u);
    EXPECT_LE (picture.headings[0].box.x1 - picture.headings[0].box.x0 + 1, 64);
    // At the left margin, where a channel's first meter starts; its width is main's 22 columns.
    const auto channel = enginePicture (1, 1, { true, true, true, true }, {}, 128, 64, {}, {});
    EXPECT_EQ (picture.meters[0].box.x0, channel.meters[0].box.x0);
    EXPECT_EQ (picture.meters[0].box.x1 - picture.meters[0].box.x0 + 1, 22);
    EXPECT_LE (picture.headings[0].box.x0, picture.meters[0].box.x0);
    EXPECT_TRUE (isEmpty (picture.cursor));
    EXPECT_TRUE (isEmpty (picture.active));
    ASSERT_TRUE (picture.toggle.has_value());
    EXPECT_EQ (picture.toggle->text, "CUE");
}

// One caption step (x0.8) below the band, as the desk's OLEDs since 2026-10-28: the letters light at most
// half the band's rows (seven of twelve before the step).
TEST (DisplayPaint, HeadingsAreACaptionStepBelowTheirBand)
{
    const auto picture = enginePicture (1, 1, { true, true, true, true }, {}, oledWidth, oledHeight, {}, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    const auto& band = picture.headings[0].box;
    int first = -1, last = -1;
    for (int y = band.y0; y <= band.y1; ++y)
        for (int x = 0; x < oledWidth; ++x)
            if (image.getPixelAt (x, y).getBrightness() > 0.5f)
            {
                if (first < 0) first = y;
                last = y;
            }
    ASSERT_GE (first, 0);
    EXPECT_LE (last - first + 1, (band.y1 - band.y0 + 1) * 0.5) << "ink rows " << first << ".." << last;
}

// A page test must paint: every meter of every panel lights for a level and stays dark in silence.
TEST (DisplayPaint, EveryPanelPaintsItsMeters)
{
    const auto litIn = [] (const juce::Image& image, const Box& b) {
        int n = 0;
        for (int x = b.x0; x <= b.x1; ++x)
            for (int y = b.y0; y <= b.y1; ++y)
                n += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
        return n;
    };
    for (const double level : { 0.6, 0.0 })
    {
        const std::array<double, 5> levels { level, level, level, level, level };
        const std::vector<Picture> pictures { enginePicture (1, 1, { true, true, true, true }, levels, oledWidth, oledHeight, {}, {}),
                                              returnPicture (false, level, oledWidth, oledHeight, false, 0.0) };
        for (const auto& picture : pictures)
        {
            const auto image = paintPicture (picture, oledWidth, oledHeight);
            ASSERT_FALSE (picture.meters.empty());
            for (const auto& m : picture.meters)
                if (level > 0)
                    EXPECT_GT (litIn (image, m.box), 0) << m.box.x0;
                else
                    EXPECT_EQ (litIn (image, m.box), 0) << m.box.x0;
        }
    }
}

// A page test must paint: the name reaches the pixels inside its heading box, and the band between the
// heading and the meter -- where a channel's arrow stands -- stays dark.
TEST (DisplayPicture, ReturnSnapshotPaintsTheNameAndNoArrow)
{
    const auto picture = returnPicture (true, 0.5, oledWidth, oledHeight, false, 0.0);
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    const int below = picture.headings[0].box.y1 + 1, above = picture.meters[0].box.y0 - 1;
    for (int y = below; y <= above; ++y)
        for (int x = 0; x < oledWidth; ++x)
            EXPECT_LE (image.getPixelAt (x, y).getBrightness(), 0.5f) << x << "," << y;
    const auto box = picture.headings[0].box;
    int lit = 0;
    for (int y = box.y0; y <= box.y1; ++y)
        for (int x = box.x0; x <= box.x1; ++x)
            lit += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
    EXPECT_GT (lit, 0);
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
    ASSERT_EQ (cases->size(), 100);
    for (const auto& c : *cases)
    {
        const auto picture = enginePicture (c["source"], c["cursor"], arrayOf<4, bool> (c["present"]),
                                            arrayOf<5, double> (c["levels"]), c["width"], c["height"],
                                            arrayOf<5, bool> (c["clips"]), arrayOf<5, double> (c["holds"]));
        expectSamePicture (picture, c["picture"], "source " + c["source"].toString() + " cursor " + c["cursor"].toString()
                                                      + " present " + juce::JSON::toString (c["present"], true));
    }
}

// A page test must paint: an absent deck keeps its letter over an empty slot, a present one a bar.
TEST (DisplayPicture, DeckChannelSnapshotPaintsAbsentDeckEmpty)
{
    const auto picture = enginePicture (0, 0, { true, false, true, true }, { 1, 1, 1, 1, 1 }, oledWidth, oledHeight,
                                        {}, {});
    const auto image = paintPicture (picture, oledWidth, oledHeight);
    ASSERT_EQ (picture.meters.size(), 5u);
    const auto lit = [&] (const Box& b) {
        int n = 0;
        for (int x = b.x0; x <= b.x1; ++x)
            for (int y = b.y0; y <= b.y1; ++y)
                n += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
        return n;
    };
    EXPECT_GT (lit (picture.meters[0].box), 0);   // D1
    EXPECT_EQ (lit (picture.meters[1].box), 0);   // D2 absent: no bar
    EXPECT_GT (lit (picture.meters[4].box), 0);   // A
    EXPECT_EQ (picture.headings[1].text, "B");   // the letter stays: five fixed slots
}

// 1 2 3 4 A, analog last (maintainer, 2026-10-26); the numbers are Core's (0 analog, k deck k).
TEST (DeskRing, EngineModeLabelsOnThePicture)
{
    const auto all = enginePicture (1, 0, { true, true, true, true }, {}, oledWidth, oledHeight, {}, {});
    ASSERT_EQ (all.headings.size(), 5u);
    const std::array<std::string, 5> names { "A", "B", "C", "D", "ST" };
    for (size_t i = 0; i < names.size(); ++i)
        EXPECT_EQ (all.headings[i].text, names[i]);
    const auto centre = [] (const Box& b) { return b.x0 + b.x1; };
    EXPECT_LE (std::abs (centre (all.cursor) - centre (all.meters[4].box)), 1);   // arrow over A
    EXPECT_EQ (all.active.x0, all.meters[0].box.x0 - 1);                          // bracket round D1
    // An absent deck keeps cursor, bracket (they are Core's) and its letter: five fixed slots.
    const auto absent = enginePicture (4, 3, { true, true, true, false }, {}, oledWidth, oledHeight, {}, {});
    EXPECT_EQ (absent.headings[3].text, "D");
    // Round 3: the scale marks stand on every slot, an absent one too.
    EXPECT_EQ (absent.marks.size(), 10u);
    EXPECT_EQ (absent.active.x0, absent.meters[3].box.x0 - 1);
    EXPECT_LE (std::abs (centre (absent.cursor) - centre (absent.meters[2].box)), 1);
}

namespace
{
const std::array<std::string, 4> someValues { "1/4", "70%", "HP 3", "60\xc2\xb0" };
}

// The desk's return with the delay list (maintainer, 2026-10-30): the hardware's rows -- BEAT, FEEDBK,
// COLOR, SPREAD under DELAY, CUE no longer one of them -- left-aligned, the VU at the right. No AUX heading:
// the VU is the delay's return, DELAY covers it, and the VU takes the panel's whole height.
TEST (DisplayPicture, TheDelayReturnHasTheRowsLeftAndTheMeterRight)
{
    const auto p = delayReturnPicture (false, 0, someValues, 0.5, oledWidth, oledHeight, false, 0.0);
    ASSERT_EQ (p.rows.size(), 4u);
    ASSERT_EQ (p.meters.size(), 1u);
    ASSERT_EQ (p.headings.size(), 1u);
    EXPECT_EQ (p.headings[0].text, "DELAY");
    EXPECT_EQ (p.headings[0].box.x0, p.rows[0].box.x0);   // the heading over the rows, at the left margin
    EXPECT_LE (p.rows[0].box.x0, 1);
    const auto& meter = p.meters[0].box;
    for (const auto& row : p.rows)
        EXPECT_LT (row.box.x1, meter.x0) << row.name;
    EXPECT_GE (meter.x1, oledWidth - 8);                   // at the right edge
    EXPECT_EQ (meter.x1 - meter.x0 + 1, 22);               // the return's meter, as wide as before
    EXPECT_EQ (meter.y0, 0);
    EXPECT_EQ (meter.y1, oledHeight - 1);
    ASSERT_EQ (p.dividers.size(), 1u);
    EXPECT_GT (p.dividers[0].x0, p.rows[0].box.x1);
    EXPECT_LT (p.dividers[0].x0, meter.x0 - 2);            // the scale marks stand left of the bar
    EXPECT_EQ (p.dividers[0].y0, 0);
    EXPECT_EQ (p.dividers[0].y1, oledHeight - 1);
    EXPECT_FALSE (p.toggle.has_value());                   // no CUE field: DELAY CUE is a key now
    EXPECT_TRUE (isEmpty (p.cursor));
    EXPECT_TRUE (isEmpty (p.active));
    const char* names[] { "BEAT", "FEEDBK", "COLOR", "SPREAD" };
    for (size_t i = 0; i < p.rows.size(); ++i)
    {
        EXPECT_EQ (p.rows[i].name, names[i]);
        EXPECT_EQ (p.rows[i].value, someValues[i]);
        EXPECT_GT (p.rows[i].box.y0, p.headings[0].box.y1);
        if (i > 0)
        {
            EXPECT_EQ (p.rows[i].box.y0, p.rows[i - 1].box.y1 + 1);
            EXPECT_EQ (p.rows[i].box.y1 - p.rows[i].box.y0, p.rows[0].box.y1 - p.rows[0].box.y0);
        }
    }
    EXPECT_EQ (p.rows.back().box.y1, oledHeight - 1);
}

// The hardware's two modes, told by what is lit: selecting, the whole row under the cursor; editing, its value.
TEST (DisplayPicture, TheCursorRowIsLitWholeWhileSelectingAndItsValueWhileEditing)
{
    const auto selecting = delayReturnPicture (false, 2, someValues, 0.0, oledWidth, oledHeight, false, 0.0);
    const auto editing = delayReturnPicture (true, 2, someValues, 0.0, oledWidth, oledHeight, false, 0.0);
    for (size_t i = 0; i < 4; ++i)
    {
        EXPECT_EQ (selecting.rows[i].lit, i == 2 ? Row::Lit::row : Row::Lit::none) << i;
        EXPECT_EQ (editing.rows[i].lit, i == 2 ? Row::Lit::value : Row::Lit::none) << i;
    }
}

// A page test must paint: the lit row is mostly white across its width, the edited one only at its right
// end, and an unlit row's name reaches the pixels.
TEST (DisplayPaint, TheDelayRowsPaintTheirLitPart)
{
    const auto litIn = [] (const juce::Image& image, int x0, int x1, const Box& b) {
        int n = 0;
        for (int x = x0; x <= x1; ++x)
            for (int y = b.y0; y <= b.y1; ++y)
                n += image.getPixelAt (x, y).getBrightness() > 0.5f ? 1 : 0;
        return n;
    };
    const auto selecting = delayReturnPicture (false, 1, someValues, 0.0, oledWidth, oledHeight, false, 0.0);
    const auto editing = delayReturnPicture (true, 1, someValues, 0.0, oledWidth, oledHeight, false, 0.0);
    const auto shotSelecting = paintPicture (selecting, oledWidth, oledHeight);
    const auto shotEditing = paintPicture (editing, oledWidth, oledHeight);
    const auto& row = selecting.rows[1].box;
    const int area = (row.x1 - row.x0 + 1) * (row.y1 - row.y0 + 1);
    const int leftEnd = row.x0 + 6;
    EXPECT_GT (litIn (shotSelecting, row.x0, row.x1, row), area / 2);
    EXPECT_GT (litIn (shotSelecting, row.x0, leftEnd, row), 0);    // the bar starts at the name
    EXPECT_GT (litIn (shotEditing, row.x1 - 3, row.x1, row), 0);   // the value's end is lit ...
    EXPECT_LT (litIn (shotEditing, row.x0, row.x1, row), area / 2);
    const auto& other = selecting.rows[3].box;
    EXPECT_GT (litIn (shotSelecting, other.x0, other.x1, other), 0);
    EXPECT_LT (litIn (shotSelecting, other.x0, other.x1, other), (other.x1 - other.x0 + 1) * (other.y1 - other.y0 + 1) / 2);
}

namespace
{
/** The rows and columns of a box that carry ink. */
juce::Rectangle<int> inkIn (const juce::Image& image, const Box& b)
{
    int top = -1, bottom = -1, left = -1, right = -1;
    for (int y = b.y0; y <= b.y1; ++y)
        for (int x = b.x0; x <= b.x1; ++x)
            if (image.getPixelAt (x, y).getBrightness() > 0.5f)
            {
                top = top < 0 ? y : top;
                bottom = y;
                left = left < 0 ? x : juce::jmin (left, x);
                right = juce::jmax (right, x);
            }
    return top < 0 ? juce::Rectangle<int>() : juce::Rectangle<int>::leftTopRightBottom (left, top, right + 1, bottom + 1);
}
}

// Maintainer, 2026-10-30: DELAY larger on the desk -- the largest size whose capitals leave two dark rows
// above and below in its band (rows 0-13) and whose text fits its box; the rows keep their place.
TEST (DisplayPaint, TheDelayHeadingIsLarge)
{
    const auto p = delayReturnPicture (false, 0, someValues, 0.0, oledWidth, oledHeight, false, 0.0);
    ASSERT_EQ (p.headings.size(), 1u);
    for (const auto& h : p.headings)
    {
        EXPECT_TRUE (h.large) << h.text;
        EXPECT_EQ (h.box.y0, 0);
        EXPECT_EQ (h.box.y1, 13);
        EXPECT_LT (h.box.y1, p.rows[0].box.y0 - 1) << h.text;
    }
    const auto image = paintPicture (p, oledWidth, oledHeight);
    const auto delayInk = inkIn (image, p.headings[0].box);
    ASSERT_FALSE (delayInk.isEmpty());
    EXPECT_GE (delayInk.getHeight(), 9);   // was 6 of the 12-row band
    EXPECT_LE (delayInk.getHeight(), 14 - 4);
    EXPECT_GE (delayInk.getY(), 2);
    EXPECT_LE (delayInk.getBottom(), 12);
}
