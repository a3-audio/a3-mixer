// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskIndicatorsUi.h"

#include "DeskLook.h"
#include "DeskTheme.h"
#include "DisplayPaint.h"

namespace desk
{
namespace
{
juce::Colour zoneColour (leds::screen::Zone zone)
{
    switch (zone)
    {
        case leds::screen::Zone::green: return theme::ledGreen;
        case leds::screen::Zone::yellow: return theme::ledYellow;
        case leds::screen::Zone::orange: return theme::ledOrange;
        case leds::screen::Zone::red: return theme::ledRed;
    }
    return theme::ledGreen;
}

/** Shares: the well's corner of its width, the gap between segments of a segment's pitch. */
constexpr float wellCornerOfWidth = 0.08f, gapOfPitch = 0.3f, holdOfSegment = 0.5f;

/** One meter, StemDeck's way: a black well, thin segments across it bottom up -- lit in their
    zone's colour, unlit as a trace of it -- and the held peak as a line atop its segment. */
template <typename ZoneOf>
void paintBar (juce::Graphics& g, juce::Rectangle<float> well, int segments, int lit, int held, ZoneOf zoneOf)
{
    g.setColour (theme::meterWell);
    g.fillRoundedRectangle (well, well.getWidth() * wellCornerOfWidth);
    const auto inner = well.reduced (juce::jmax (1.f, well.getWidth() * 0.08f), juce::jmax (1.f, well.getWidth() * 0.04f));
    const float pitch = inner.getHeight() / static_cast<float> (segments);
    const float light = juce::jmax (1.f, pitch * (1.f - gapOfPitch));
    const auto segmentAt = [&] (int i) {
        return juce::Rectangle<float> (inner.getX(), inner.getBottom() - pitch * static_cast<float> (i + 1), inner.getWidth(), light);
    };
    for (int i = 0; i < segments; ++i)
    {
        const auto colour = zoneColour (zoneOf (i));
        g.setColour (i < lit ? colour : colour.withAlpha (theme::ledOffAlpha));
        g.fillRect (segmentAt (i));
    }
    if (held <= lit)
        return;
    g.setColour (zoneColour (zoneOf (held - 1)));
    g.fillRect (segmentAt (held - 1).removeFromTop (juce::jmax (1.f, light * holdOfSegment)));
}
}

int LedColumn::segments() const { return leds::screen::channelSegments (static_cast<float> (getHeight())); }

void LedColumn::setLevels (double barDb, double holdDb)
{
    _barDb = barDb;
    _holdDb = holdDb;
    const int n = segments();
    const int lit = leds::screen::channelSegmentsLit (barDb, n), held = leds::screen::channelSegmentsLit (holdDb, n);
    if (lit == _lit && held == _held)
        return;
    _lit = lit;
    _held = held;
    repaint();
}

void LedColumn::paint (juce::Graphics& g)
{
    g.fillAll (theme::panelSeen (isEnabled()));
    const DimWhenDisabled dim (g, isEnabled());   // stale: the whole surface dims (spec 4.1)
    const int n = segments();
    const auto bounds = getLocalBounds().toFloat();
    paintBar (g, bounds.withSizeKeepingCentre (bounds.getWidth() * 0.7f, bounds.getHeight()), n,
              leds::screen::channelSegmentsLit (_barDb, n), leds::screen::channelSegmentsLit (_holdDb, n),
              [n] (int i) { return leds::screen::channelSegmentZone (i, n); });
}

OutputMatrix::OutputMatrix()
{
    setOpaque (true);
    _barDb.fill (leds::meterFloorDb);
    _holdDb.fill (leds::meterFloorDb);
}

int OutputMatrix::segments() const { return leds::screen::mainSegments (static_cast<float> (getHeight())); }

void OutputMatrix::setColumn (int column, double barDb, double holdDb)
{
    if (column < 0 || column >= leds::matrixColumns)
        return;
    const auto c = (size_t) column;
    _barDb[c] = barDb;
    _holdDb[c] = holdDb;
    const int n = segments();
    const int lit = leds::screen::mainSegmentsLit (barDb, n), held = leds::screen::mainSegmentsLit (holdDb, n);
    if (_lit[c] == lit && _held[c] == held)
        return;
    _lit[c] = lit;
    _held[c] = held;
    repaint();
}

void OutputMatrix::paint (juce::Graphics& g)
{
    g.fillAll (theme::panelSeen (isEnabled()));
    const DimWhenDisabled dim (g, isEnabled());   // stale: the whole surface dims (spec 4.1)
    const int n = segments();
    const float cw = static_cast<float> (getWidth()) / leds::matrixColumns;
    for (int c = 0; c < leds::matrixColumns; ++c)
    {
        const auto column = juce::Rectangle<float> (static_cast<float> (c) * cw, 0.f, cw, static_cast<float> (getHeight()));
        paintBar (g, column.withSizeKeepingCentre (cw * 0.6f, column.getHeight()), n,
                  leds::screen::mainSegmentsLit (_barDb[(size_t) c], n), leds::screen::mainSegmentsLit (_holdDb[(size_t) c], n),
                  [n] (int i) { return leds::screen::mainSegmentZone (i, n); });
    }
}

void OledView::setPicture (const display::Picture& picture)
{
    _picture = picture;
    _image = display::paintPicture (picture, display::oledWidth, display::oledHeight);
    repaint();
}

juce::Rectangle<float> OledView::panelArea() const
{
    const auto bounds = getLocalBounds().toFloat();
    const float scale = juce::jmin (bounds.getWidth() / display::oledWidth, bounds.getHeight() / display::oledHeight);
    return bounds.withSizeKeepingCentre (display::oledWidth * scale, display::oledHeight * scale);
}

void OledView::paint (juce::Graphics& g)
{
    g.fillAll (theme::panelSeen (isEnabled()));
    const DimWhenDisabled dim (g, isEnabled());   // stale: the whole surface dims (spec 4.1)
    if (! _image.isValid())
        return;
    g.setImageResamplingQuality (juce::Graphics::lowResamplingQuality);   // pixels stay pixels
    g.drawImage (_image, panelArea(), juce::RectanglePlacement::stretchToFit);
}

void OledView::mouseUp (const juce::MouseEvent& e)
{
    if (! onSlot || e.mouseWasDraggedSinceMouseDown())
        return;
    const auto area = panelArea();
    const int px = static_cast<int> ((e.position.x - area.getX()) / area.getWidth() * display::oledWidth);
    for (size_t i = 0; i < _picture.meters.size(); ++i)
        if (px >= _picture.meters[i].box.x0 - 1 && px <= _picture.meters[i].box.x1 + 1)
            return onSlot (static_cast<int> (i));
    if (_picture.toggle && px >= _picture.toggle->box.x0 && px <= _picture.toggle->box.x1)
        onSlot (static_cast<int> (_picture.meters.size()));
}

void StatusLine::setText (juce::String left, juce::String right)
{
    if (left == _left && right == _right)
        return;
    _left = std::move (left);
    _right = std::move (right);
    repaint();
}

void StatusLine::setLive (LiveChip chip)
{
    if (chip.offered == _live.offered && chip.lit == _live.lit && chip.tappable == _live.tappable)
        return;
    _live = chip;
    repaint();
}

juce::Rectangle<float> StatusLine::liveChip() const
{
    if (! _live.offered)
        return {};
    auto line = getLocalBounds().toFloat();
    const auto chip = line.removeFromRight (line.getWidth() * liveChipWidth);
    return chip.withSizeKeepingCentre (chip.getWidth(), chip.getHeight() * liveChipHeight);
}

void StatusLine::mouseUp (const juce::MouseEvent& e)
{
    // One finger arrives as touch#0 and X's emulated mouse#0: only the mouse acts (as Motion does).
    if (! onLiveTapped || e.source.isTouch() || e.mouseWasDraggedSinceMouseDown())
        return;
    if (liveChip().contains (e.position))
        onLiveTapped();
}

void StatusLine::paint (juce::Graphics& g)
{
    g.setColour (theme::caption);
    g.setFont (juce::FontOptions (static_cast<float> (getHeight()) * 0.75f));
    const auto chip = liveChip();
    auto textArea = getLocalBounds();
    if (! chip.isEmpty())
        textArea.removeFromRight (getWidth() - juce::roundToInt (chip.getX()));
    g.drawText (_left, textArea, juce::Justification::centredLeft, true);
    g.drawText (_right, textArea, juce::Justification::centredRight, true);
    if (! chip.isEmpty())
        paintLiveChip (g, chip);
}

void StatusLine::paintLiveChip (juce::Graphics& g, juce::Rectangle<float> chip) const
{
    // Lit is the one coloured thing on the line (colour is state): another party may operate the room.
    // Dark is a key at rest; dimmed when a tap would do nothing (no hands), never hidden.
    const float corner = chip.getHeight() * 0.25f;
    const DimWhenDisabled dim (g, _live.lit || _live.tappable);
    g.setColour (_live.lit ? theme::lampLive : theme::keyFace);
    g.fillRoundedRectangle (chip, corner);
    g.setColour (_live.lit ? theme::background : theme::caption);
    g.setFont (juce::FontOptions (chip.getHeight() * 0.62f, _live.lit ? juce::Font::bold : juce::Font::plain));
    g.drawText (_live.lit ? "PRO-DJ LIVE" : "pro-DJ", chip, juce::Justification::centred, true);
}
}
