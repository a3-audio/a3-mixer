// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <optional>

#include <juce_gui_basics/juce_gui_basics.h>

namespace desk
{
/** Every control dims through this one scope: whatever is painted while it
    lives comes out at theme::alphaDisabled if the control is disabled. */
class DimWhenDisabled
{
public:
    DimWhenDisabled (juce::Graphics& g, bool enabled);
    ~DimWhenDisabled();
    DimWhenDisabled (const DimWhenDisabled&) = delete;
    DimWhenDisabled& operator= (const DimWhenDisabled&) = delete;

private:
    juce::Graphics& _g;
    bool _dimmed;
};

class DeskLook : public juce::LookAndFeel_V4
{
public:
    DeskLook();
    void drawRotarySlider (juce::Graphics&, int x, int y, int width, int height, float position,
                           float startAngle, float endAngle, juce::Slider&) override;
    void drawLinearSlider (juce::Graphics&, int x, int y, int width, int height, float position,
                           float minPosition, float maxPosition, juce::Slider::SliderStyle, juce::Slider&) override;
    /** A fader's travel is the cap centre's travel: the region JUCE drags over,
        the one it draws in and the one DeskFader grabs in are the same. */
    juce::Slider::SliderLayout getSliderLayout (juce::Slider&) override;

    /** `arcValue` empty: no arc (unknown, or an encoder, which is endless). */
    static void paintKnob (juce::Graphics& g, juce::Rectangle<float> cell, const juce::String& caption,
                           std::optional<float> arcValue, float pointerValue, juce::Colour arc,
                           bool fromMiddle, bool marked, float startAngle, float endAngle);
    /** An endless encoder: a closed, knurled ring and a cap turned `clicks` steps from noon. */
    static void paintEncoder (juce::Graphics& g, juce::Rectangle<float> cell, const juce::String& caption, int clicks);
};
}
