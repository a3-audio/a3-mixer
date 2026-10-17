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
// Shares of the window's height unless named otherwise. Read off the V02
// photo (spec §4.2); Task D3 replaces them with the measured front panel.
constexpr float gapOfWidth = 0.02f, masterColumns = 1.6f;
constexpr float status = 0.02f, top = 0.075f, display = 0.07f, encoder = 0.05f, pot = 0.058f;
constexpr float tap = 0.035f, keys = 0.05f, caption = 0.03f;
constexpr float matrix = 0.20f, matrixCaption = 0.03f, filterPots = 0.075f, filterKeys = 0.05f;
constexpr float master = 0.12f, monitorPots = 0.075f, phones = 0.075f;
constexpr float meterOfColumn = 0.25f, capOfFaderWidth = 0.45f;
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
    const float gap = gapOfWidth * width;
    const float column = (width - 6.f * gap) / (static_cast<float> (numChannels) + masterColumns);
    const auto xOf = [&] (int i) { return area.getX() + gap + static_cast<float> (i) * (column + gap); };

    float y = area.getY();
    const auto row = [&] (float share) {
        const Rect r { 0.f, y, 0.f, share * height };
        y += share * height;
        return r;
    };
    const auto at = [] (Rect band, float x, float w) { return band.withX (x).withWidth (w); };

    const auto statusBand = row (status);
    l.status = at (statusBand, area.getX() + gap, width - 2.f * gap);
    const auto topBand = row (top);
    l.returnDisplay = at (topBand, xOf (0), column);
    l.select = at (topBand, xOf (1), column);
    l.auxReturn = at (topBand, xOf (2), column);
    const auto displayBand = row (display);
    const auto encoderBand = row (encoder);
    std::array<Rect, 5> potBands;
    for (auto& band : potBands)
        band = row (pot);
    const auto tapBand = row (tap);
    const auto keysBand = row (keys);
    const float captionHeight = caption * height;
    const Rect restBand { 0.f, y, 0.f, area.getBottom() - y - captionHeight };
    const Rect captionBand { 0.f, area.getBottom() - captionHeight, 0.f, captionHeight };

    for (int i = 0; i < numChannels; ++i)
    {
        auto& s = l.strips[(size_t) i];
        const float x = xOf (i);
        s.display = at (displayBand, x, column);
        s.encoder = at (encoderBand, x, column);
        for (size_t p = 0; p < s.pots.size(); ++p)
            s.pots[p] = at (potBands[p], x, column);
        s.tap = at (tapBand, x, column);
        s.fx = at (keysBand, x, column * 0.5f);
        s.cue = at (keysBand, x + column * 0.5f, column * 0.5f);
        s.meter = at (restBand, x, column * meterOfColumn);
        s.fader = at (restBand, x + column * meterOfColumn, column * (1.f - meterOfColumn));
        s.caption = at (captionBand, x, column);
    }

    const float mx = xOf (numChannels), mw = masterColumns * column;
    y = topBand.getY();
    const auto whole = [&] (float share) { return at (row (share), mx, mw); };
    const auto halves = [&] (float share, Rect& left, Rect& right) {
        const auto band = row (share);
        left = at (band, mx, mw * 0.5f);
        right = at (band, mx + mw * 0.5f, mw * 0.5f);
    };
    l.matrix = whole (matrix);
    l.matrixCaption = whole (matrixCaption);
    halves (filterPots, l.freq, l.res);
    halves (filterKeys, l.hpf, l.lpf);
    l.master = whole (master);
    halves (monitorPots, l.booth, l.cueMix);
    halves (phones, l.phones, l.lock);

    const auto targets = touchTargets (l);
    l.fits = std::all_of (targets.begin(), targets.end(), [fingertip] (const Rect& r) {
        return std::min (r.getWidth(), r.getHeight()) >= fingertip;
    });
    return l;
}

std::vector<Rect> touchTargets (const DeskLayout& l)
{
    std::vector<Rect> targets { l.select, l.auxReturn, l.freq, l.res, l.hpf, l.lpf,
                                l.master, l.booth, l.cueMix, l.phones, l.lock };
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
