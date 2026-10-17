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
/** A channel's 8 input LEDs in the firmware's colours, bottom up, and the hold LED. Opaque: repainted at meter pace. */
class LedColumn : public juce::Component
{
public:
    LedColumn() { setOpaque (true); }
    void setLeds (int lit, int holdIndex);
    void paint (juce::Graphics&) override;

private:
    int _lit = 0, _hold = -1;
};

/** The 8 x 32 output matrix: SUB, 1-7; the bar and its held dot. */
class OutputMatrix : public juce::Component
{
public:
    OutputMatrix() { setOpaque (true); }
    /** A column outside 0-7 is ignored. */
    void setColumn (int column, int bar, int hold);
    void paint (juce::Graphics&) override;

private:
    std::array<int, leds::matrixColumns> _bar {}, _hold {};
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
    void setText (juce::String left, juce::String right);
    void paint (juce::Graphics&) override;

private:
    juce::String _left, _right;
};
}
