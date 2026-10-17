// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>

#include <juce_graphics/juce_graphics.h>

namespace desk::theme
{
inline const juce::Colour background { 0xff121418 }, ringTrack { 0xff353a42 }, cap { 0xff2a2e35 },
    pointer { 0xffe8eaed }, caption { 0xffa9aeb6 }, neutralArc { 0xffd8dbe0 }, marker { 0xfffafafa },
    keyFace { 0xff23272d }, keyFaceLit { 0xff30353d }, slot { 0xff050607 }, tick { 0xff3a3f47 },
    ledOff { 0xff24282e }, ledGreen { 0xff5fd27a }, ledYellow { 0xfff2b33d }, ledRed { 0xffe8453c };
/** The lamps keep the hardware's colours: the eye knows them from the desk (spec 4.1).
    filter.led: blue HPF, green LPF (truth). */
inline const juce::Colour lampFx { 0xff6bd66b }, lampCue { 0xff3d7bf0 }, lampTap { 0xffe04040 },
    lampHpf { 0xff3d7bf0 }, lampLpf { 0xff6bd66b }, lampLock { 0xfff2b33d };
/** Channel identity, as on Motion: only on value arcs and fader caps. */
inline const std::array<juce::Colour, 4> channel { juce::Colour (0xffe8336d), juce::Colour (0xff5468e8),
                                                   juce::Colour (0xfff2c21b), juce::Colour (0xff1fa39a) };
inline constexpr float alphaDisabled = 0.35f;
}
