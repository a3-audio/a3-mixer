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
juce::Colour ledColour (int index)
{
    switch (leds::channelLedColour (index))
    {
        case leds::LedColour::green: return theme::ledGreen;
        case leds::LedColour::yellow: return theme::ledYellow;
        case leds::LedColour::red: return theme::ledRed;
    }
    return theme::ledOff;
}
}

void LedColumn::setLeds (int lit, int holdIndex)
{
    if (lit == _lit && holdIndex == _hold)
        return;
    _lit = lit;
    _hold = holdIndex;
    repaint();
}

void LedColumn::paint (juce::Graphics& g)
{
    g.fillAll (theme::background);
    const DimWhenDisabled dim (g, isEnabled());   // stale: the whole surface dims (spec 4.1)
    const float cell = static_cast<float> (getHeight()) / leds::channelLedCount;
    const float d = juce::jmin (cell, static_cast<float> (getWidth())) * 0.6f;
    for (int i = 0; i < leds::channelLedCount; ++i)
    {
        const bool on = i < _lit || i == _hold;
        g.setColour (on ? ledColour (i) : theme::ledOff);
        const float cy = static_cast<float> (getHeight()) - (static_cast<float> (i) + 0.5f) * cell;
        g.fillEllipse (static_cast<float> (getWidth()) * 0.5f - d * 0.5f, cy - d * 0.5f, d, d);
    }
}

void OutputMatrix::setColumn (int column, int bar, int hold)
{
    if (column < 0 || column >= leds::matrixColumns)
        return;
    if (_bar[(size_t) column] == bar && _hold[(size_t) column] == hold)
        return;
    _bar[(size_t) column] = bar;
    _hold[(size_t) column] = hold;
    repaint();
}

void OutputMatrix::paint (juce::Graphics& g)
{
    g.fillAll (theme::background);
    const DimWhenDisabled dim (g, isEnabled());   // stale: the whole surface dims (spec 4.1)
    const float cw = static_cast<float> (getWidth()) / leds::matrixColumns, ch = static_cast<float> (getHeight()) / leds::mainLedCount;
    const float d = juce::jmin (cw, ch) * 0.7f;
    for (int c = 0; c < leds::matrixColumns; ++c)
        for (int row = 0; row < leds::mainLedCount; ++row)
        {
            const bool held = row == _hold[(size_t) c] && row > _bar[(size_t) c];
            g.setColour (row <= _bar[(size_t) c] ? theme::ledGreen : held ? theme::ledYellow : theme::ledOff);
            const float x = (static_cast<float> (c) + 0.5f) * cw, y = static_cast<float> (getHeight()) - (static_cast<float> (row) + 0.5f) * ch;
            g.fillEllipse (x - d * 0.5f, y - d * 0.5f, d, d);
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
    g.fillAll (theme::background);
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
    g.setColour (_live.lit ? theme::lampLock : theme::keyFace);
    g.fillRoundedRectangle (chip, corner);
    g.setColour (_live.lit ? theme::background : theme::caption);
    g.setFont (juce::FontOptions (chip.getHeight() * 0.62f, _live.lit ? juce::Font::bold : juce::Font::plain));
    g.drawText (_live.lit ? "PRO-DJ LIVE" : "pro-DJ", chip, juce::Justification::centred, true);
}
}
