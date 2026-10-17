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
constexpr float dragOfKnobForFullTurn = 4.f;
}

DeskKnob::DeskKnob (juce::String c, juce::Colour a, bool middle) : caption (std::move (c)), arc (a), fromMiddle (middle)
{
    setSliderStyle (juce::Slider::RotaryVerticalDrag);
    setTextBoxStyle (juce::Slider::NoTextBox, true, 0, 0);
    setRange (0.0, 1.0);
    setRotaryParameters (startAngle, endAngle, true);
    setDoubleClickReturnValue (false, 0.0);
}

void DeskKnob::resized()
{
    juce::Slider::resized();   // the base sets the draw area; without it the knob paints in 0 x 0
    // A full turn for four knob heights of drag: the same feel at every window size.
    setMouseDragSensitivity (juce::jmax (1, juce::roundToInt (dragOfKnobForFullTurn * static_cast<float> (getHeight()))));
}

DeskFader::DeskFader (juce::Colour c) : colour (c)
{
    setSliderStyle (juce::Slider::LinearVertical);
    setTextBoxStyle (juce::Slider::NoTextBox, true, 0, 0);
    setRange (0.0, 1.0);
    setSliderSnapsToMousePosition (false);
    setDoubleClickReturnValue (false, 0.0);
}

bool DeskFader::hitTest (int x, int y)
{
    return faderCap (getLocalBounds().toFloat(), static_cast<float> (valueToProportionOfLength (getValue())))
        .contains (static_cast<float> (x), static_cast<float> (y));
}

DeskEncoder::DeskEncoder (juce::String caption) : _caption (std::move (caption)) {}

void DeskEncoder::paint (juce::Graphics& g)
{
    const DimWhenDisabled dim (g, isEnabled());
    DeskLook::paintKnob (g, getLocalBounds().toFloat(), _caption, std::nullopt, 0.5f, theme::neutralArc, false,
                         false, startAngle, endAngle);
}

void DeskEncoder::mouseDown (const juce::MouseEvent&)
{
    _drag.emplace (turns::dragPerClickOfKnob * static_cast<float> (getHeight()));
    _moved = false;
}

void DeskEncoder::mouseDrag (const juce::MouseEvent& e)
{
    if (! _drag)
        return;
    const auto clicks = _drag->feed (static_cast<float> (-e.getDistanceFromDragStartY()));
    if (clicks == 0)
        return;
    _moved = true;
    if (onTurn)
        onTurn (clicks);
}

void DeskEncoder::mouseUp (const juce::MouseEvent&)
{
    if (! _moved && onPush)
        onPush();
    _drag.reset();
}

void DeskEncoder::mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails& wheel)
{
    if (wheel.deltaY != 0.f && onTurn)
        onTurn (wheel.deltaY > 0.f ? 1 : -1);
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
    const DimWhenDisabled dim (g, isEnabled());
    auto r = getLocalBounds().toFloat().reduced (juce::jmin (getWidth(), getHeight()) * 0.06f);
    const float corner = r.getHeight() * 0.12f;
    g.setColour (_lit ? theme::keyFaceLit : theme::keyFace);
    g.fillRoundedRectangle (r, corner);
    if (_lit)
    {
        g.setColour (_lamp);
        g.fillRoundedRectangle (r.withHeight (r.getHeight() * 0.12f).reduced (r.getWidth() * 0.12f, 0.f), corner * 0.5f);
    }
    g.setColour (_lit ? theme::pointer : theme::caption);
    g.setFont (juce::FontOptions (r.getHeight() * 0.32f, _lit ? juce::Font::bold : juce::Font::plain));
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
