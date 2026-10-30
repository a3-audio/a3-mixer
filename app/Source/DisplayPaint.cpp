// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DisplayPaint.h"

namespace desk::display
{
namespace
{
// One caption step (x0.8, the designer's type scale) below the box, as the desk's OLEDs since 2026-10-28.
constexpr float textOfHeading = 0.9f, textStep = 0.8f;
constexpr int frame = 1, toggleInset = 3, clipHatch = 3;
// The hardware's list (a3_mixer_displays): dark columns at a row's ends and least between name and value.
constexpr int rowPad = 2, rowTextGap = 4;
constexpr float capOfFont = 0.72f;

juce::Rectangle<int> rectOf (const Box& b) { return { b.x0, b.y0, b.x1 - b.x0 + 1, b.y1 - b.y0 + 1 }; }
Box inset (const Box& b, int n) { return { b.x0 + n, b.y0 + n, b.x1 - n, b.y1 - n }; }

void text (juce::Graphics& g, const Box& box, const juce::String& t)
{
    const auto r = rectOf (box);
    g.setFont (juce::FontOptions (static_cast<float> (r.getHeight()) * textOfHeading * textStep));
    g.drawFittedText (t, r, juce::Justification::centred, 1, 0.5f);
}

void letters (juce::Graphics& g, const Box& box, const juce::String& t)
{
    const int rows = (box.y1 - box.y0 + 1) / juce::jmax (1, t.length());
    const int top = box.y0 + (box.y1 - box.y0 + 1 - rows * t.length()) / 2;
    for (int i = 0; i < t.length(); ++i)
        text (g, { box.x0, top + i * rows, box.x1, top + (i + 1) * rows - 1 }, juce::String::charToString (t[i]));
}

float textWidth (const juce::Font& font, const juce::String& t) { return juce::GlyphArrangement::getStringWidth (font, t); }

/** The one font all rows are set in (a3_mixer_displays._row_font): the row's height, shrunk until the
    capitals leave a dark row above and below and the longest name beside the longest value fits. */
juce::Font rowFont (const std::vector<Row>& rows)
{
    const auto& b = rows.front().box;
    const int width = b.x1 - b.x0 + 1, height = b.y1 - b.y0 + 1;
    float names = 0.f, values = 0.f;
    for (float size = static_cast<float> (height); size > 4.f; size -= 0.5f)
    {
        const juce::Font font (juce::FontOptions { size });
        names = values = 0.f;
        for (const auto* sample : { "SPREAD", "FEEDBK" })
            names = juce::jmax (names, textWidth (font, sample));
        for (const auto* sample : { "HP 10", "LP 10", "100%", "180\xc2\xb0", "1/8", "3/4" })
            values = juce::jmax (values, textWidth (font, juce::String::fromUTF8 (sample)));
        if (size * capOfFont <= static_cast<float> (height - 2) && names + rowTextGap + values <= width - 2 * rowPad)
            return font;
    }
    return juce::Font (juce::FontOptions { 4.f });
}

void delayRows (juce::Graphics& g, const std::vector<Row>& rows)
{
    if (rows.empty())
        return;
    const auto font = rowFont (rows);
    g.setFont (font);
    for (const auto& row : rows)
    {
        const auto box = rectOf (row.box);
        const auto value = juce::String::fromUTF8 (row.value.c_str());
        const int valueAt = box.getRight() - rowPad - juce::roundToInt (textWidth (font, value));
        g.setColour (juce::Colours::white);
        if (row.lit == Row::Lit::row)
            g.fillRect (box);
        else if (row.lit == Row::Lit::value)
            g.fillRect (box.withLeft (valueAt - rowPad));
        g.setColour (row.lit == Row::Lit::row ? juce::Colours::black : juce::Colours::white);
        g.drawText (juce::String::fromUTF8 (row.name.c_str()), box.withTrimmedLeft (rowPad), juce::Justification::centredLeft, false);
        g.setColour (row.lit != Row::Lit::none ? juce::Colours::black : juce::Colours::white);
        g.drawText (value, box.withLeft (valueAt), juce::Justification::centredLeft, false);
    }
    g.setColour (juce::Colours::white);
}

void meter (juce::Image& image, juce::Graphics& g, const Meter& m)
{
    const auto& b = m.box;
    if (const auto hold = m.holdRow())
        g.fillRect (b.x0, *hold, b.x1 - b.x0 + 1, 1);
    const int bar = m.pixels();
    if (bar == 0)
        return;
    const int top = b.y1 - bar + 1;
    g.fillRect (b.x0, top, b.x1 - b.x0 + 1, bar);
    if (m.hatched())
        for (int x = b.x0; x <= b.x1; ++x)
            for (int y = top; y <= b.y1; ++y)
                if ((x + y) % clipHatch == 0)
                    image.setPixelAt (x, y, juce::Colours::black);
}
}

juce::Image paintPicture (const Picture& p, int width, int height)
{
    juce::Image image (juce::Image::RGB, width, height, true);
    juce::Graphics g (image);
    g.setColour (juce::Colours::white);
    for (const auto& h : p.headings)
        text (g, h.box, h.text);
    for (const auto& d : p.dividers)
        g.fillRect (rectOf (d));
    for (const auto& m : p.marks)
        g.fillRect (rectOf (m));
    for (const auto& m : p.meters)
        meter (image, g, m);
    if (p.toggle)
    {
        const auto field = inset (p.toggle->box, toggleInset);
        if (p.toggle->on)
            g.fillRect (rectOf (field));
        else
            g.drawRect (rectOf (field), 1);
        g.setColour (p.toggle->on ? juce::Colours::black : juce::Colours::white);
        letters (g, inset (field, frame), p.toggle->text);
        g.setColour (juce::Colours::white);
    }
    delayRows (g, p.rows);
    const auto& a = p.active;
    if (a.x1 >= a.x0 && a.y1 >= a.y0)   // an empty box is "no bracket"
    {
        g.fillRect (a.x0, a.y0, a.x1 - a.x0 + 1, 1);
        g.fillRect (a.x0, a.y0, 1, a.y1 - a.y0 + 1);
        g.fillRect (a.x1, a.y0, 1, a.y1 - a.y0 + 1);
    }
    const auto& c = p.cursor;
    for (int row = 0, y = c.y0; y <= c.y1 && c.x0 + row <= c.x1 - row; ++row, ++y)
        g.fillRect (c.x0 + row, y, (c.x1 - row) - (c.x0 + row) + 1, 1);
    return image;
}
}
