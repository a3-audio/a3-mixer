// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <array>
#include <vector>

#include <juce_graphics/juce_graphics.h>

#include "DeskControls.h"

namespace desk
{
using Rect = juce::Rectangle<float>;

struct StripLayout
{
    Rect display, encoder;
    std::array<Rect, 5> pots;   // channelPotKeys 0-4: SEND, TRIM, HIGH, MID, LOW
    Rect tap, fx, cue, meter, fader, caption;
};

struct DeskLayout
{
    Rect status, returnDisplay, select, auxReturn;
    std::array<StripLayout, numChannels> strips;
    Rect matrix, matrixCaption, freq, res, hpf, lpf, master, booth, cueMix, phones, lock;
    float fingertip = 0.f;
    bool fits = false;
};

/** The hardware front panel's width : height (spec §4.2; photo, measured in T0). */
inline constexpr float deskAspect = 0.62f;
/** The one absolute size: a fingertip does not scale with the window. */
inline constexpr float fingertipMm = 7.f;

float fingertipPixels (double dpi, double scale);
DeskLayout layOutDesk (Rect area, float fingertip);
Rect faderCap (Rect fader, float value);
/** Everything a hand aims at. The display slots are not among them: the
    encoder is the way to the cursor, a slot tap a convenience. */
std::vector<Rect> touchTargets (const DeskLayout& layout);
/** The smallest window at which every touch target is still a fingertip. */
juce::Point<int> minimumDeskSize (float fingertip);
}
