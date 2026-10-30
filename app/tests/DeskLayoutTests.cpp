// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <gtest/gtest.h>

#include <vector>

#include "DeskLayout.h"

using namespace desk;

namespace
{
constexpr float finger = 26.f;
const juce::Rectangle<float> roomy { 0.f, 0.f, 1000.f * deskAspect, 1000.f };
// The rig's screen, the desk fullscreen beside the StemDecks.
const juce::Rectangle<float> rig { 0.f, 0.f, 768.f, 1024.f };

std::vector<Rect> everythingDrawn (const DeskLayout& l)
{
    // The fader, not its cap: the cap rides inside it.
    std::vector<Rect> drawn { l.status, l.returnDisplay, l.select, l.auxReturn, l.matrix, l.matrixCaption, l.freq, l.res,
                              l.hpf, l.lpf, l.master, l.booth, l.cueMix, l.phones, l.lock };
    for (const auto& s : l.strips)
    {
        drawn.insert (drawn.end(), { s.display, s.encoder, s.tap, s.fx, s.cue, s.meter, s.fader, s.caption });
        drawn.insert (drawn.end(), s.pots.begin(), s.pots.end());
    }
    return drawn;
}
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
    EXPECT_NEAR (l.masterCard.getWidth(), 1.6f * l.strips[0].card.getWidth(), 0.5f);
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

// The V02 photo: the display encoders' caps are no smaller than the pots'.
TEST (DeskLayout, TheEncoderIsAsLargeAsAPot)
{
    const auto l = layOutDesk (roomy, finger);
    for (const auto& s : l.strips)
        EXPECT_GE (s.encoder.getHeight() + 0.01f, s.pots[0].getHeight());
}

// StemDeck on the same screen: its transport band and library run from 658 to 1016 of 1024
// (stemdeck-C.png, 2026-10-30). The faders stand in that band, so the composite lines up.
TEST (DeskLayout, TheFaderZoneIsStemDecksBottomBand)
{
    EXPECT_NEAR (stemDeckBandTop, 658.f / 1024.f, 1e-6f);
    EXPECT_NEAR (stemDeckBandBottom, 1016.f / 1024.f, 1e-6f);
    for (const auto& area : { rig, roomy })
    {
        const auto l = layOutDesk (area, finger);
        for (const auto& s : l.strips)
        {
            EXPECT_NEAR (s.faderCard.getY(), stemDeckBandTop * area.getHeight(), 0.5f);
            EXPECT_NEAR (s.faderCard.getBottom(), stemDeckBandBottom * area.getHeight(), 0.5f);
            EXPECT_TRUE (s.faderCard.contains (s.fader)) << s.fader.toString();
            EXPECT_TRUE (s.faderCard.contains (s.meter)) << s.meter.toString();
            EXPECT_GT (s.fader.getHeight(), 0.8f * s.faderCard.getHeight());
            EXPECT_FLOAT_EQ (s.meter.getY(), s.fader.getY());
            EXPECT_FLOAT_EQ (s.meter.getBottom(), s.fader.getBottom());
        }
    }
}

TEST (DeskLayout, TheMasterSectionIsAsTallAsTheFaderZone)
{
    const auto l = layOutDesk (rig, finger);
    EXPECT_FLOAT_EQ (l.masterCard.getY(), l.strips[0].faderCard.getY());
    EXPECT_FLOAT_EQ (l.masterCard.getBottom(), l.strips[0].faderCard.getBottom());
    for (const auto& r : { l.freq, l.res, l.hpf, l.lpf, l.master, l.booth, l.cueMix, l.phones, l.lock })
        EXPECT_TRUE (l.masterCard.contains (r)) << r.toString();
}

TEST (DeskLayout, TheOutputMetersFillTheUpperMasterColumn)
{
    const auto l = layOutDesk (rig, finger);
    EXPECT_TRUE (l.outputCard.contains (l.matrix));
    EXPECT_TRUE (l.outputCard.contains (l.matrixCaption));
    EXPECT_LT (l.outputCard.getBottom(), l.masterCard.getY());
    EXPECT_GT (l.matrix.getHeight(), 0.5f * rig.getHeight());
}

TEST (DeskLayout, EveryStripIsACardAboveItsFaderCard)
{
    const auto l = layOutDesk (rig, finger);
    for (const auto& s : l.strips)
    {
        for (const auto& r : { s.display, s.encoder, s.pots[0], s.pots[4], s.tap, s.fx, s.cue })
            EXPECT_TRUE (s.card.contains (r)) << r.toString();
        EXPECT_LT (s.card.getBottom(), s.faderCard.getY());
        EXPECT_FLOAT_EQ (s.card.getX(), s.faderCard.getX());
        EXPECT_FLOAT_EQ (s.card.getWidth(), s.faderCard.getWidth());
    }
    for (const auto& r : { l.returnDisplay, l.select, l.auxReturn })
        EXPECT_TRUE (l.returnCard.contains (r)) << r.toString();
}

TEST (DeskLayout, NothingOverlapsAtTheRigSize)
{
    const auto l = layOutDesk (rig, finger);
    EXPECT_TRUE (l.fits);
    const auto drawn = everythingDrawn (l);
    for (size_t i = 0; i < drawn.size(); ++i)
    {
        EXPECT_TRUE (rig.contains (drawn[i])) << drawn[i].toString();
        for (size_t j = i + 1; j < drawn.size(); ++j)
            EXPECT_LT (drawn[i].getIntersection (drawn[j]).getHeight() * drawn[i].getIntersection (drawn[j]).getWidth(), 1.f)
                << drawn[i].toString() << " / " << drawn[j].toString();
    }
    std::vector<Rect> cards { l.returnCard, l.outputCard, l.masterCard };
    for (const auto& s : l.strips)
        cards.insert (cards.end(), { s.card, s.faderCard });
    for (size_t i = 0; i < cards.size(); ++i)
        for (size_t j = i + 1; j < cards.size(); ++j)
            EXPECT_FALSE (cards[i].intersects (cards[j])) << cards[i].toString() << " / " << cards[j].toString();
}
