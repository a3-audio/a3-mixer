// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include "DeskLayout.h"

using namespace desk;

namespace
{
constexpr float finger = 26.f;
const juce::Rectangle<float> roomy { 0.f, 0.f, 1000.f * deskAspect, 1000.f };
}

TEST (DeskLayout, EverythingLiesInsideTheWindow)
{
    const auto l = layOutDesk (roomy, finger);
    for (const auto& r : touchTargets (l))
        EXPECT_TRUE (roomy.contains (r)) << r.toString();
    EXPECT_TRUE (roomy.contains (l.matrix));
}

TEST (DeskLayout, FourStripsThenTheMasterColumn)
{
    const auto l = layOutDesk (roomy, finger);
    for (int i = 1; i < 4; ++i)
        EXPECT_GT (l.strips[(size_t) i].pots[0].getX(), l.strips[(size_t) i - 1].pots[0].getRight());
    EXPECT_GT (l.master.getX(), l.strips[3].pots[0].getRight());
    EXPECT_NEAR (l.master.getWidth(), 1.6f * l.strips[0].pots[0].getWidth(), 0.5f);
}

TEST (DeskLayout, TheStripReadsTopToBottomAsTheHardware)
{
    // Bound to a named layout: a reference into the temporary would dangle.
    const auto l = layOutDesk (roomy, finger);
    const auto& s = l.strips[0];
    EXPECT_LT (s.display.getBottom(), s.encoder.getY() + 0.5f);
    EXPECT_LT (s.encoder.getBottom(), s.pots[0].getY() + 0.5f);
    for (size_t p = 1; p < s.pots.size(); ++p)
        EXPECT_LT (s.pots[p - 1].getBottom(), s.pots[p].getY() + 0.5f);
    EXPECT_LT (s.pots[4].getBottom(), s.tap.getY() + 0.5f);
    EXPECT_LT (s.tap.getBottom(), s.fx.getY() + 0.5f);
    EXPECT_FLOAT_EQ (s.fx.getY(), s.cue.getY());
    EXPECT_LT (s.fx.getBottom(), s.fader.getY() + 0.5f);
    EXPECT_LT (s.meter.getRight(), s.fader.getX() + 0.5f);
}

TEST (DeskLayout, TheTopBandSitsOverChannelsOneToThree)
{
    const auto l = layOutDesk (roomy, finger);
    EXPECT_FLOAT_EQ (l.returnDisplay.getX(), l.strips[0].display.getX());
    EXPECT_FLOAT_EQ (l.select.getX(), l.strips[1].display.getX());
    EXPECT_FLOAT_EQ (l.auxReturn.getX(), l.strips[2].display.getX());
    EXPECT_LT (l.returnDisplay.getBottom(), l.strips[0].display.getY() + 0.5f);
}

TEST (DeskLayout, AtTheMinimumEveryTargetIsAFingertip)
{
    const auto least = minimumDeskSize (finger);
    const auto at = layOutDesk ({ 0.f, 0.f, (float) least.x, (float) least.y }, finger);
    EXPECT_TRUE (at.fits);
    for (const auto& r : touchTargets (at))
        EXPECT_GE (juce::jmin (r.getWidth(), r.getHeight()), finger - 0.01f) << r.toString();
    const auto below = layOutDesk ({ 0.f, 0.f, deskAspect * (float) (least.y - 1), (float) (least.y - 1) }, finger);
    EXPECT_FALSE (below.fits);
}

TEST (DeskLayout, TheFingertipIsPhysical)
{
    EXPECT_NEAR (fingertipPixels (96.0, 1.0), 26.46f, 0.01f);
    EXPECT_NEAR (fingertipPixels (192.0, 2.0), 26.46f, 0.01f);
    EXPECT_NEAR (fingertipPixels (0.0, 1.0), 26.46f, 0.01f);   // unknown dpi: 96
}

TEST (DeskLayout, TheFaderCapRidesItsSlot)
{
    const juce::Rectangle<float> fader { 0.f, 0.f, 40.f, 400.f };
    EXPECT_FLOAT_EQ (faderCap (fader, 0.f).getBottom(), 400.f);
    EXPECT_FLOAT_EQ (faderCap (fader, 1.f).getY(), 0.f);
    EXPECT_FLOAT_EQ (faderCap (fader, 0.5f).getWidth(), 40.f);
}
