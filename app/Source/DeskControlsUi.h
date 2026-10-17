// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <functional>
#include <optional>

#include <juce_gui_basics/juce_gui_basics.h>

#include "EncoderTurns.h"

namespace desk
{
/** A pot: JUCE's rotary slider, dragged vertically, wheel for fine steps.
    No double-click to rest (spec Q10: a reset mid-set is a jump on the PA). */
class DeskKnob : public juce::Slider
{
public:
    DeskKnob (juce::String caption, juce::Colour arc, bool fromMiddle);
    void resized() override;

    juce::String caption;
    juce::Colour arc;
    bool fromMiddle = false, known = false, marked = false;
};

/** A fader: grabbed by its cap only, then following the hand; a tap on the
    slot does nothing -- a desk fader never jumps to the finger (spec 4.3). */
class DeskFader : public juce::Slider
{
public:
    explicit DeskFader (juce::Colour colour);
    bool hitTest (int x, int y) override;

    juce::Colour colour;
    bool known = false, marked = false;
};

/** An endless push encoder: drag or wheel turns, a click without a drag pushes. */
class DeskEncoder : public juce::Component
{
public:
    explicit DeskEncoder (juce::String caption);
    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails&) override;

    std::function<void (int clicks)> onTurn;
    std::function<void()> onPush;

private:
    juce::String _caption;
    std::optional<turns::DragClicks> _drag;
    bool _moved = false;
};

/** A key: press and release go out as they happen; lit by Core's lamp. */
class DeskKey : public juce::Component
{
public:
    DeskKey (juce::String caption, juce::Colour lamp);
    void setLit (bool lit);
    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;

    std::function<void (bool down)> onPress;

private:
    juce::String _caption;
    juce::Colour _lamp;
    bool _lit = false;
};
}
