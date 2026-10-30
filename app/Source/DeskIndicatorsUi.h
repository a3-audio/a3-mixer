// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <functional>

#include <juce_gui_basics/juce_gui_basics.h>

#include "DisplayPicture.h"
#include "LedScale.h"

namespace desk
{
/** A channel's input meter: the screen's finer scale (leds::screen), bottom up, and its held peak
    as a line. Opaque: repainted at meter pace, only when a segment changes. */
class LedColumn : public juce::Component
{
public:
    LedColumn() { setOpaque (true); }
    void setLevels (double barDb, double holdDb);
    void paint (juce::Graphics&) override;

private:
    int segments() const;

    double _barDb = leds::meterFloorDb, _holdDb = leds::meterFloorDb;
    int _lit = 0, _held = 0;
};

/** The output meters: SUB, 1-7, each a bar on the screen's finer scale and its held peak. */
class OutputMatrix : public juce::Component
{
public:
    OutputMatrix();
    /** A column outside 0-7 is ignored. */
    void setColumn (int column, double barDb, double holdDb);
    void paint (juce::Graphics&) override;

private:
    int segments() const;

    std::array<double, leds::matrixColumns> _barDb {}, _holdDb {};
    std::array<int, leds::matrixColumns> _lit {}, _held {};
};

/** A display, the OLED's picture at its own pixels, scaled whole -- the same picture as the hardware's. */
class OledView : public juce::Component
{
public:
    OledView() { setOpaque (true); }
    void setPicture (const display::Picture& picture);
    void paint (juce::Graphics&) override;
    void mouseUp (const juce::MouseEvent&) override;

    /** A tap on a slot, as an index into the picture's meters (a return's CUE field: meters.size()). */
    std::function<void (int index)> onSlot;

private:
    juce::Rectangle<float> panelArea() const;

    display::Picture _picture;
    juce::Image _image;
};

class StatusLine : public juce::Component
{
public:
    /** The pro-DJ LIVE chip at the line's right end: offered only when the truth has the word. */
    struct LiveChip
    {
        bool offered = false, lit = false, tappable = false;
    };

    void setText (juce::String left, juce::String right);
    void setLive (LiveChip chip);
    /** The chip's area in the line's own coordinates; empty when it is not offered. */
    juce::Rectangle<float> liveChip() const;
    void paint (juce::Graphics&) override;
    void mouseUp (const juce::MouseEvent&) override;

    std::function<void()> onLiveTapped;

private:
    void paintLiveChip (juce::Graphics&, juce::Rectangle<float> chip) const;

    /** Shares: the chip's width of the line, its height of the line's. */
    static constexpr float liveChipWidth = 0.2f, liveChipHeight = 0.9f;

    juce::String _left, _right;
    LiveChip _live;
};
}
