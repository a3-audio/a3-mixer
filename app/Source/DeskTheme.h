// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>

#include <juce_graphics/juce_graphics.h>

namespace desk::theme
{
/** StemDeck's colours (stemdeck/Source/Theme.h): the desk stands beside the decks on the rig's
    screens and belongs to the same family (maintainer, 2026-10-30: "Design like stemdeck"). */
inline const juce::Colour background { 0xff121315 }, panel { 0xff1c1d20 }, panelRaised { 0xff26282c },
    outline { 0xff34363b }, text { 0xffdcdcdc }, textDim { 0xff8b8e94 };

inline const juce::Colour ringTrack = outline, pointer = text, caption = textDim, keyFace = panelRaised,
    tick = outline;
inline const juce::Colour neutralArc { 0xffd8dbe0 }, marker { 0xfffafafa }, slot { 0xff000000 },
    capTop { 0xff4a4d53 }, capBottom { 0xff2b2d31 }, bodyTop { 0xff3a3d42 }, bodyBottom { 0xff222428 };
/** A meter's ground: StemDeck's meters are black wells in the card. */
inline const juce::Colour meterWell { 0xff000000 };
/** StemDeck's meter colours, with an orange between its yellow and its red. */
inline const juce::Colour ledGreen { 0xff3ec46d }, ledYellow { 0xffe8c33d }, ledOrange { 0xffe8873d },
    ledRed { 0xffe04848 };
/** An unlit segment: its own colour at this alpha over the well, as on StemDeck. */
inline constexpr float ledOffAlpha = 0.12f;
/** The lamps keep the hardware's colours: the eye knows them from the desk (spec 4.1).
    filter.led: blue HPF, green LPF (truth). */
inline const juce::Colour lampFx { 0xff6bd66b }, lampCue { 0xff3d7bf0 }, lampTap { 0xffe04040 },
    lampHpf { 0xff3d7bf0 }, lampLpf { 0xff6bd66b }, lampLive { 0xfff2b33d };
/** Channel identity, as on Motion: on value arcs, fader caps and the line atop the strip's card. */
inline const std::array<juce::Colour, 4> channel { juce::Colour (0xffe8336d), juce::Colour (0xff5468e8),
                                                   juce::Colour (0xfff2c21b), juce::Colour (0xff1fa39a) };
inline constexpr float alphaDisabled = 0.35f;

/** A card's corner as on StemDeck: a share of its shorter side. */
inline float corner (juce::Rectangle<float> area) { return juce::jmin (area.getWidth(), area.getHeight()) * 0.035f; }

/** What a card looks like through the dimming of a stale desk: an opaque child on a card fills with this. */
inline juce::Colour panelSeen (bool enabled) { return enabled ? panel : background.interpolatedWith (panel, alphaDisabled); }
}
