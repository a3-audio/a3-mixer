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
    Two taps put it at restPosition() where it has one (set by DeskComponent;
    the maintainer's call of 2026-10-17 over spec Q10). */
class DeskKnob : public juce::Slider
{
public:
    DeskKnob (juce::String caption, juce::Colour arc, bool fromMiddle);
    void resized() override;
    /** Only a known value can be grabbed, as with the fader. */
    bool hitTest (int x, int y) override;

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
    void resized() override;
    /** Only a drawn (known) cap can be grabbed. */
    bool hitTest (int x, int y) override;

    juce::Colour colour;
    bool known = false, marked = false;
};

/** An endless push encoder: drag or wheel turns, a click without a drag pushes.
    Its cap turns a step per click sent: the selection itself is the display's. */
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
    void turn (int clicks);

    juce::String _caption;
    std::optional<turns::DragClicks> _drag;
    bool _turned = false;
    int _clicks = 0;
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
