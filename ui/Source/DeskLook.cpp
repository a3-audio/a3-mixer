// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskLook.h"

#include "DeskControlsUi.h"
#include "DeskLayout.h"
#include "DeskTheme.h"

namespace desk
{
namespace
{
// StemDeck's knob (Theme.cpp drawRotarySlider): shares of the knob's radius. Its caption as
// StemDeck's: a line under the knob, the text 0.85 of the line.
constexpr float textOfCaption = 0.85f, knobOfSpace = 0.9f;
constexpr float strokeOfRadius = 0.18f, bodyInsetOfStroke = 2.2f;
/** The encoder's knurl, and the step its cap turns per click: a step the eye
    can follow, not the hardware's detent count (unmeasured, a3_mixer_encoders). */
constexpr int knurlsPerTurn = 24;

juce::Point<float> onCircle (juce::Point<float> centre, float radius, float angle)
{
    return centre.getPointOnCircumference (radius, angle);
}

void arcPath (juce::Graphics& g, juce::Point<float> c, float r, float from, float to, float stroke)
{
    juce::Path p;
    p.addCentredArc (c.x, c.y, r, r, 0.f, from, to, true);
    g.strokePath (p, juce::PathStrokeType (stroke, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
}

float capHeightOf (const juce::Slider& fader)
{
    return faderCap (fader.getLocalBounds().toFloat(), 0.f).getHeight();
}

/** StemDeck's fader: tick marks either side of a black slot, a wide cap in a gradient with the
    strip's colour as its line. The cap fills the hit area faderCap() gives. */
void paintFaderSlot (juce::Graphics& g, juce::Rectangle<float> bounds)
{
    const auto slot = bounds.withSizeKeepingCentre (bounds.getWidth() * 0.12f, bounds.getHeight());
    const float tickGap = slot.getWidth() * 0.5f;
    g.setColour (theme::tick);
    for (int t = 0; t <= 10; ++t)
    {
        const float ty = bounds.getY() + bounds.getHeight() * static_cast<float> (t) / 10.f;
        const float tick = bounds.getWidth() * (t % 5 == 0 ? 0.22f : 0.13f);
        g.fillRect (slot.getX() - tickGap - tick, ty, tick, 1.f);
        g.fillRect (slot.getRight() + tickGap, ty, tick, 1.f);
    }
    g.setColour (theme::slot);
    g.fillRoundedRectangle (slot, slot.getWidth() * 0.5f);
}

void paintFaderCap (juce::Graphics& g, juce::Rectangle<float> cap, const DeskFader& fader)
{
    const auto body = cap.reduced (cap.getWidth() * 0.04f, 0.f);
    g.setGradientFill (juce::ColourGradient (theme::capTop, 0.f, body.getY(), theme::capBottom, 0.f, body.getBottom(), false));
    g.fillRoundedRectangle (body, body.getHeight() * 0.12f);
    g.setColour (fader.colour);
    g.fillRect (body.withSizeKeepingCentre (body.getWidth() * 0.85f, juce::jmax (2.f, body.getHeight() * 0.1f)));
}
}

DimWhenDisabled::DimWhenDisabled (juce::Graphics& g, bool enabled) : _g (g), _dimmed (! enabled)
{
    if (_dimmed)
        _g.beginTransparencyLayer (theme::alphaDisabled);
}

DimWhenDisabled::~DimWhenDisabled()
{
    if (_dimmed)
        _g.endTransparencyLayer();
}

DeskLook::DeskLook()
{
    setColour (juce::ResizableWindow::backgroundColourId, theme::background);
}

namespace
{
/** Where a knob's parts sit in its cell: one geometry for pots and encoders. */
struct KnobParts
{
    juce::Rectangle<float> caption;
    juce::Point<float> centre;
    float stroke, ring, cap;
};

KnobParts partsOf (juce::Rectangle<float> cell, std::optional<float> captionHeight = std::nullopt)
{
    KnobParts k;
    k.caption = cell.removeFromBottom (captionHeight.value_or (cell.getHeight() * DeskLook::captionOfCell));
    const float radius = juce::jmin (cell.getWidth(), cell.getHeight()) * knobOfSpace * 0.5f;
    k.centre = cell.getCentre();
    k.stroke = juce::jmax (1.5f, radius * strokeOfRadius);
    k.ring = radius - k.stroke * 0.5f;
    k.cap = radius - k.stroke * bodyInsetOfStroke;
    return k;
}

void paintCap (juce::Graphics& g, const KnobParts& k, float pointerAngle, const juce::String& caption)
{
    g.setGradientFill (juce::ColourGradient (theme::bodyTop, k.centre.x, k.centre.y - k.cap, theme::bodyBottom, k.centre.x,
                                             k.centre.y + k.cap, false));
    g.fillEllipse (k.centre.x - k.cap, k.centre.y - k.cap, 2.f * k.cap, 2.f * k.cap);
    juce::Path pointer;
    const float width = juce::jmax (1.5f, k.cap * 0.2f);
    pointer.addRoundedRectangle (-width * 0.5f, -k.cap * 0.9f, width, k.cap * 0.5f, width * 0.5f);
    g.setColour (theme::pointer);
    g.fillPath (pointer, juce::AffineTransform::rotation (pointerAngle).translated (k.centre));
    g.setColour (theme::caption);
    g.setFont (juce::FontOptions (k.caption.getHeight() * textOfCaption));
    g.drawFittedText (caption, k.caption.toNearestInt(), juce::Justification::centred, 1, 0.8f);
}
}

void DeskLook::paintKnob (juce::Graphics& g, juce::Rectangle<float> cell, const juce::String& caption,
                          std::optional<float> arcValue, float pointerValue, juce::Colour arc, bool fromMiddle,
                          float startAngle, float endAngle, std::optional<float> captionHeight)
{
    const auto k = partsOf (cell, captionHeight);
    g.setColour (theme::ringTrack);
    arcPath (g, k.centre, k.ring, startAngle, endAngle, k.stroke);
    const auto angleOf = [&] (float v) { return startAngle + juce::jlimit (0.f, 1.f, v) * (endAngle - startAngle); };
    if (arcValue)
    {
        g.setColour (arc);
        const float from = fromMiddle ? angleOf (0.5f) : startAngle;
        arcPath (g, k.centre, k.ring, juce::jmin (from, angleOf (*arcValue)), juce::jmax (from, angleOf (*arcValue)), k.stroke);
    }
    paintCap (g, k, angleOf (pointerValue), caption);
}

void DeskLook::paintEncoder (juce::Graphics& g, juce::Rectangle<float> cell, const juce::String& caption, int clicks)
{
    // Endless, so no travel and no value arc: a closed ring, knurled like the
    // hardware's encoder cap -- what tells it from the pots below at a glance.
    const auto k = partsOf (cell);
    constexpr float fullTurn = juce::MathConstants<float>::twoPi;
    g.setColour (theme::ringTrack);
    arcPath (g, k.centre, k.ring, 0.f, fullTurn, k.stroke);
    g.setColour (theme::textDim);
    for (int i = 0; i < knurlsPerTurn; ++i)
    {
        const float a = fullTurn * static_cast<float> (i) / static_cast<float> (knurlsPerTurn);
        g.drawLine ({ onCircle (k.centre, k.ring - k.stroke * 0.3f, a), onCircle (k.centre, k.ring + k.stroke * 0.3f, a) },
                    juce::jmax (1.f, k.stroke * 0.2f));
    }
    paintCap (g, k, fullTurn * static_cast<float> (clicks) / static_cast<float> (knurlsPerTurn), caption);
}

void DeskLook::drawRotarySlider (juce::Graphics& g, int x, int y, int width, int height, float position,
                                 float startAngle, float endAngle, juce::Slider& slider)
{
    auto* knob = dynamic_cast<DeskKnob*> (&slider);
    if (knob == nullptr)
        return LookAndFeel_V4::drawRotarySlider (g, x, y, width, height, position, startAngle, endAngle, slider);
    const DimWhenDisabled dim (g, slider.isEnabled());
    paintKnob (g, juce::Rectangle<int> (x, y, width, height).toFloat(), knob->caption,
               knob->known ? std::optional<float> (position) : std::nullopt, position, knob->arc,
               knob->fromMiddle, startAngle, endAngle, knob->captionHeight);
}

juce::Slider::SliderLayout DeskLook::getSliderLayout (juce::Slider& slider)
{
    if (dynamic_cast<DeskFader*> (&slider) == nullptr)
        return LookAndFeel_V4::getSliderLayout (slider);
    // The handle's centre travels from half a cap above the bottom to half a cap below the top.
    const float inset = capHeightOf (slider) * 0.5f;
    juce::Slider::SliderLayout layout;
    layout.sliderBounds = slider.getLocalBounds().toFloat().reduced (0.f, inset).toNearestInt();
    return layout;
}

void DeskLook::drawLinearSlider (juce::Graphics& g, int x, int y, int width, int height, float position, float,
                                 float, juce::Slider::SliderStyle style, juce::Slider& slider)
{
    auto* fader = dynamic_cast<DeskFader*> (&slider);
    if (fader == nullptr)
        return LookAndFeel_V4::drawLinearSlider (g, x, y, width, height, position, 0.f, 0.f, style, slider);
    const DimWhenDisabled dim (g, slider.isEnabled());
    const auto whole = slider.getLocalBounds().toFloat();
    paintFaderSlot (g, whole);
    if (! fader->known)
        return;
    const float capHeight = capHeightOf (slider);
    paintFaderCap (g, { whole.getX(), position - capHeight * 0.5f, whole.getWidth(), capHeight }, *fader);
}
}
