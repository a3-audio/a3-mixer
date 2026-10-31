// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskControlsUi.h"

#include "DeskLayout.h"
#include "DeskLook.h"
#include "DeskTheme.h"

namespace desk
{
namespace
{
constexpr float startAngle = juce::MathConstants<float>::pi * 1.2f;
constexpr float endAngle = juce::MathConstants<float>::pi * 2.8f;
}

DeskKnob::DeskKnob (juce::String c, juce::Colour a, bool middle) : caption (std::move (c)), arc (a), fromMiddle (middle)
{
    setSliderStyle (juce::Slider::RotaryVerticalDrag);
    setTextBoxStyle (juce::Slider::NoTextBox, true, 0, 0);
    setRange (0.0, 1.0);
    setRotaryParameters (startAngle, endAngle, true);
}

void DeskKnob::resized()
{
    juce::Slider::resized();   // the base sets the draw area; without it the knob paints in 0 x 0
    applyDragSensitivity();
}

void DeskKnob::setFullTurnDrag (float pixels)
{
    _fullTurnDrag = pixels;
    applyDragSensitivity();
}

void DeskKnob::applyDragSensitivity()
{
    // A full turn for four knob heights of drag: the same feel at every window size.
    const float drag = _fullTurnDrag.value_or (dragOfKnobForFullTurn * static_cast<float> (getHeight()));
    setMouseDragSensitivity (juce::jmax (1, juce::roundToInt (drag)));
}

bool DeskKnob::hitTest (int x, int y)
{
    return known && juce::Slider::hitTest (x, y);
}

DeskFader::DeskFader (juce::Colour c) : colour (c)
{
    setSliderStyle (juce::Slider::LinearVertical);
    setTextBoxStyle (juce::Slider::NoTextBox, true, 0, 0);
    setRange (0.0, 1.0);
    setSliderSnapsToMousePosition (false);
}

void DeskFader::resized()
{
    juce::Slider::resized();
    // One pixel of drag per pixel of cap travel: the cap stays under the finger.
    const float travel = static_cast<float> (getHeight()) - faderCap (getLocalBounds().toFloat(), 0.f).getHeight();
    setMouseDragSensitivity (juce::jmax (1, juce::roundToInt (travel)));
}

bool DeskFader::hitTest (int x, int y)
{
    if (! known)
        return false;
    return faderCap (getLocalBounds().toFloat(), static_cast<float> (valueToProportionOfLength (getValue())))
        .contains (static_cast<float> (x), static_cast<float> (y));
}

DeskEncoder::DeskEncoder (juce::String caption) : _caption (std::move (caption)) {}

void DeskEncoder::paint (juce::Graphics& g)
{
    const DimWhenDisabled dim (g, isEnabled());
    DeskLook::paintEncoder (g, getLocalBounds().toFloat(), _caption, _clicks);
}

void DeskEncoder::turn (int clicks)
{
    _clicks += clicks;
    repaint();
    if (onTurn)
        onTurn (clicks);
}

void DeskEncoder::mouseDown (const juce::MouseEvent&)
{
    _drag.emplace (turns::dragPerClickOfKnob * static_cast<float> (getHeight()));
    _turned = false;
}

void DeskEncoder::mouseDrag (const juce::MouseEvent& e)
{
    if (! _drag)
        return;
    const auto clicks = _drag->feed (static_cast<float> (-e.getDistanceFromDragStartY()));
    if (clicks == 0)
        return;
    _turned = true;
    turn (clicks);
}

void DeskEncoder::mouseUp (const juce::MouseEvent& e)
{
    // JUCE's own threshold for "was a drag": a wobble is not a push.
    if (! _turned && ! e.mouseWasDraggedSinceMouseDown() && onPush)
        onPush();
    _drag.reset();
}

void DeskEncoder::mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails& wheel)
{
    if (wheel.deltaY != 0.f)
        turn (wheel.deltaY > 0.f ? 1 : -1);
}

DeskKey::DeskKey (juce::String caption, juce::Colour lamp) : _caption (std::move (caption)), _lamp (lamp) {}

void DeskKey::setLit (bool lit)
{
    if (lit == _lit)
        return;
    _lit = lit;
    repaint();
}

void DeskKey::paint (juce::Graphics& g)
{
    // StemDeck's keys: a raised tile with an outline; lit, it is filled with its lamp.
    const DimWhenDisabled dim (g, isEnabled());
    auto r = getLocalBounds().toFloat().reduced (juce::jmin (getWidth(), getHeight()) * 0.06f);
    const float corner = juce::jmin (r.getWidth(), r.getHeight()) * 0.1f;
    g.setColour (_lit ? _lamp : theme::keyFace);
    g.fillRoundedRectangle (r, corner);
    if (! _lit)
    {
        g.setColour (theme::outline);
        g.drawRoundedRectangle (r, corner, 1.f);
    }
    g.setColour (_lit ? theme::background : theme::text);
    g.setFont (juce::FontOptions (juce::jmin (r.getHeight() * 0.36f, r.getWidth() * 0.3f), _lit ? juce::Font::bold : juce::Font::plain));
    g.drawText (_caption, r, juce::Justification::centred, false);
}

void DeskKey::mouseDown (const juce::MouseEvent&)
{
    if (onPress)
        onPress (true);
}

void DeskKey::mouseUp (const juce::MouseEvent&)
{
    if (onPress)
        onPress (false);
}
}
