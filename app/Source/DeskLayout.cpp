// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskLayout.h"

#include <algorithm>
#include <cmath>

namespace desk
{
namespace shares
{
// Shares of the window's width: the margins and the gaps between cards, the padding inside one.
constexpr float gapOfWidth = 0.01f, padOfWidth = 0.01f, masterColumns = 1.6f;
// Shares of the window's height. StemDeck leaves 5 of 1024 px between its cards.
constexpr float status = 0.02f, top = 0.07f, cardGap = 5.f / 1024.f, caption = 0.025f, matrixCaption = 0.035f;
// Within a strip card, weights of its height, read off the V02 photo (spec §4.2). The encoder
// row is a pot row: the photo's display encoders are no smaller than the pots.
constexpr float display = 0.07f, pot = 0.058f, encoder = pot, tap = 0.035f, keys = 0.05f;
// Within the master card, weights of its height.
constexpr float filterPots = 0.075f, filterKeys = 0.05f, monitorPots = 0.075f;
// MASTER and BOOTH over the output meters, a share of the window's height: the size MASTER had in the master card.
constexpr float levels = 0.105f;
// The workspace key: StemDeck's and A3 Motion's app key (switcherGeometry), shares of the window's width.
constexpr float workspaceOfWidth = 80.f / 768.f, workspaceMarginOfWidth = 6.f / 768.f;
constexpr float meterOfColumn = 0.25f, capOfFaderWidth = 0.45f;
}

namespace
{
/** Hands out a band's rows top down, each its weight's share of the band. */
class Rows
{
public:
    Rows (Rect band, float totalWeight) : _x (band.getX()), _w (band.getWidth()), _y (band.getY()),
                                          _scale (band.getHeight() / totalWeight) {}
    Rect next (float weight)
    {
        const Rect r { _x, _y, _w, weight * _scale };
        _y += r.getHeight();
        return r;
    }

private:
    float _x, _w, _y, _scale;
};

/** The left and right half of a row. */
void halves (Rect row, Rect& left, Rect& right)
{
    left = row.withWidth (row.getWidth() * 0.5f);
    right = left.withX (left.getRight());
}
}

float fingertipPixels (double dpi, double scale)
{
    const double perInch = dpi > 0.0 ? dpi : 96.0;
    return static_cast<float> (fingertipMm / 25.4 * perInch / (scale > 0.0 ? scale : 1.0));
}

Rect faderCap (Rect fader, float value)
{
    const float capHeight = shares::capOfFaderWidth * fader.getWidth();
    const float travel = fader.getHeight() - capHeight;
    const float y = fader.getBottom() - capHeight - std::clamp (value, 0.f, 1.f) * travel;
    return { fader.getX(), y, fader.getWidth(), capHeight };
}

DeskLayout layOutDesk (Rect area, float fingertip)
{
    using namespace shares;
    DeskLayout l;
    l.fingertip = fingertip;
    const float width = area.getWidth(), height = area.getHeight();
    const float gap = gapOfWidth * width, pad = padOfWidth * width;
    const float column = (width - 6.f * gap) / (static_cast<float> (numChannels) + masterColumns);
    const auto xOf = [&] (int i) { return area.getX() + gap + static_cast<float> (i) * (column + gap); };
    const auto yAt = [&] (float share) { return area.getY() + share * height; };
    const auto card = [] (float x, float w, float y, float bottom) { return Rect { x, y, w, bottom - y }; };

    // The status line is as tall as the workspace key at its right end needs: a fingertip at least.
    const float statusHeight = std::max (status * height, fingertip);
    const float keyWidth = std::max (workspaceOfWidth * width, fingertip);
    l.workspace = { area.getRight() - workspaceMarginOfWidth * width - keyWidth, area.getY(), keyWidth, statusHeight };
    l.status = { area.getX() + gap, area.getY(), l.workspace.getX() - gap - (area.getX() + gap), statusHeight };

    // The FX Return over channels 1-3: its display, SELECT, its pot. The card spans all four
    // strips, so the cards below line up with one above.
    const float topY = l.status.getBottom();
    l.returnCard = card (xOf (0), xOf (numChannels - 1) + column - xOf (0), topY, topY + top * height + 2.f * pad);
    const auto topRow = l.returnCard.reduced (0.f, pad);
    l.returnDisplay = topRow.withX (xOf (0) + pad).withWidth (column - 2.f * pad);
    l.select = l.returnDisplay.withX (xOf (1) + pad);
    l.auxReturn = l.returnDisplay.withX (xOf (2) + pad);

    const float bandTop = yAt (stemDeckBandTop), bandBottom = yAt (stemDeckBandBottom);
    const float upperBottom = bandTop - cardGap * height;
    const float stripTop = l.returnCard.getBottom() + cardGap * height;
    for (int i = 0; i < numChannels; ++i)
    {
        auto& s = l.strips[(size_t) i];
        const float x = xOf (i);
        s.card = card (x, column, stripTop, upperBottom);
        Rows rows (s.card.reduced (pad), display + encoder + 5.f * pot + tap + keys);
        s.display = rows.next (display);
        s.encoder = rows.next (encoder);
        for (auto& p : s.pots)
            p = rows.next (pot);
        s.tap = rows.next (tap);
        halves (rows.next (keys), s.fx, s.cue);

        s.faderCard = card (x, column, bandTop, bandBottom);
        auto inside = s.faderCard.reduced (pad);
        s.caption = inside.removeFromBottom (caption * height);
        s.meter = inside.removeFromLeft (inside.getWidth() * meterOfColumn);
        s.fader = inside;
    }

    const float mx = xOf (numChannels), mw = masterColumns * column;
    l.outputCard = card (mx, mw, topY, upperBottom);
    auto outputs = l.outputCard.reduced (pad);
    halves (outputs.removeFromTop (levels * height), l.master, l.booth);
    l.matrixCaption = outputs.removeFromBottom (matrixCaption * height);
    l.matrix = outputs;

    l.masterCard = card (mx, mw, bandTop, bandBottom);
    Rows rows (l.masterCard.reduced (pad), filterPots + filterKeys + monitorPots);
    halves (rows.next (filterPots), l.freq, l.res);
    halves (rows.next (filterKeys), l.hpf, l.lpf);
    halves (rows.next (monitorPots), l.cueMix, l.phones);

    const auto targets = touchTargets (l);
    l.fits = std::all_of (targets.begin(), targets.end(), [fingertip] (const Rect& r) {
        return std::min (r.getWidth(), r.getHeight()) >= fingertip;
    });
    return l;
}

std::vector<Rect> touchTargets (const DeskLayout& l)
{
    std::vector<Rect> targets { l.workspace, l.select, l.auxReturn, l.freq, l.res, l.hpf, l.lpf,
                                l.master, l.booth, l.cueMix, l.phones };
    for (const auto& s : l.strips)
    {
        targets.insert (targets.end(), { s.encoder, s.tap, s.fx, s.cue, faderCap (s.fader, 0.f) });
        targets.insert (targets.end(), s.pots.begin(), s.pots.end());
    }
    return targets;
}

juce::Point<int> minimumDeskSize (float fingertip)
{
    constexpr int tallest = 4000;
    for (int h = 100; h <= tallest; ++h)
    {
        const float w = deskAspect * static_cast<float> (h);
        if (layOutDesk ({ 0.f, 0.f, w, static_cast<float> (h) }, fingertip).fits)
            return { static_cast<int> (std::ceil (w)), h };
    }
    return { static_cast<int> (deskAspect * tallest), tallest };
}
}
