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

juce::Rectangle<float> StatusLine::textArea() const
{
    auto area = getLocalBounds().toFloat();
    if (const auto chip = liveChip(); ! chip.isEmpty())
        area.setRight (chip.getX());
    return area;
}

namespace
{
// Shares of the line's height: the text's font at most, and the least it shrinks to before parts go.
constexpr float textOfLine = 0.62f, leastTextOfLine = 0.4f, chipTextOfChip = 0.62f, sizeStep = 0.5f;
const juce::String partBreak ("  ");

float widthIn (float fontHeight, const juce::String& text)
{
    return juce::GlyphArrangement::getStringWidth (juce::Font (juce::FontOptions { fontHeight }), text);
}

float lineWidth (float fontHeight, const juce::String& left, const juce::String& right)
{
    const float gap = left.isEmpty() || right.isEmpty() ? 0.f : fontHeight;
    return widthIn (fontHeight, left) + gap + widthIn (fontHeight, right);
}

juce::StringArray partsOf (const juce::String& text)
{
    juce::StringArray parts;
    auto rest = text;
    for (int at = rest.indexOf (partBreak); at >= 0; at = rest.indexOf (partBreak))
    {
        parts.add (rest.substring (0, at));
        rest = rest.substring (at + partBreak.length()).trimStart();
    }
    parts.add (rest);
    return parts;
}

/** `text` without its last words, as long as needed, the cut marked with an ellipsis. */
juce::String wordsThatFit (float fontHeight, const juce::String& text, float width)
{
    const auto ellipsis = juce::String::fromUTF8 ("\xe2\x80\xa6");
    auto words = juce::StringArray::fromTokens (text, " ", "");
    while (words.size() > 1)
    {
        words.remove (words.size() - 1);
        const auto shown = words.joinIntoString (" ") + ellipsis;
        if (widthIn (fontHeight, shown) <= width)
            return shown;
    }
    return words.joinIntoString (" ") + ellipsis;
}
}

StatusLine::Fit StatusLine::fit (const juce::String& left, const juce::String& right, juce::Rectangle<float> area)
{
    const float width = area.getWidth(), least = area.getHeight() * leastTextOfLine;
    for (float size = area.getHeight() * textOfLine; size >= least; size -= sizeStep)
        if (lineWidth (size, left, right) <= width)
            return { size, left, right };
    // At the least size: whole parts go from the end, then the name, then words of what is left.
    const auto parts = partsOf (right);
    for (const auto& name : { left, juce::String() })
        for (int count = parts.size(); count >= 1; --count)
        {
            const auto shown = juce::StringArray (parts.begin(), count).joinIntoString (partBreak);
            if (lineWidth (least, name, shown) <= width)
                return { least, name, shown };
        }
    return { least, {}, wordsThatFit (least, parts[0], width) };
}

juce::Font StatusLine::chipFont (bool lit, juce::Rectangle<float> chip)
{
    const auto style = lit ? juce::Font::bold : juce::Font::plain;
    const juce::String words (lit ? "PRO-DJ LIVE" : "pro-DJ");
    for (float size = chip.getHeight() * chipTextOfChip; size > 1.f; size -= sizeStep)
    {
        const juce::Font font (juce::FontOptions (size, style));
        if (juce::GlyphArrangement::getStringWidth (font, words) <= chip.getWidth())
            return font;
    }
    return juce::Font (juce::FontOptions (1.f, style));
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
    const auto area = textArea();
    const auto shown = fit (_left, _right, area);
    g.setFont (juce::FontOptions (shown.fontHeight));
    g.drawText (shown.left, area, juce::Justification::centredLeft, false);
    g.drawText (shown.right, area, juce::Justification::centredRight, false);
    if (const auto chip = liveChip(); ! chip.isEmpty())
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
    g.setFont (chipFont (_live.lit, chip));
    g.drawText (_live.lit ? "PRO-DJ LIVE" : "pro-DJ", chip, juce::Justification::centred, false);
}
}
