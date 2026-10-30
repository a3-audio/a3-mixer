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
    /** The strip's two cards, as StemDeck's: display to keys above, meter and fader in the bottom band. */
    Rect card, faderCard;
    Rect display, encoder;
    std::array<Rect, 5> pots;   // channelPotKeys 0-4: SEND, TRIM, HIGH, MID, LOW
    Rect tap, fx, cue, meter, fader, caption;
};

struct DeskLayout
{
    /** The status line and, at its right end, the key to the next workspace. */
    Rect status, workspace, returnCard, returnDisplay, select, auxReturn;
    std::array<StripLayout, numChannels> strips;
    /** The master column: the output meters above, the master section in the faders' band. */
    Rect outputCard, matrix, matrixCaption;
    /** MASTER and BOOTH, the room's levels, at the very top of the output card (maintainer, 2026-10-30). */
    Rect master, booth;
    Rect masterCard, freq, res, hpf, lpf, cueMix, phones;
    float fingertip = 0.f;
    bool fits = false;
};

/** The hardware front panel's width : height (spec §4.2; photo, measured in T0). */
inline constexpr float deskAspect = 0.62f;
/** StemDeck's bottom band -- its transport band and library -- as shares of its 1024 px screen:
    measured on stemdeck-C.png (2026-10-30), from the top of the LOOP/CUE/PLAY card (658) to the
    bottom of the library card (1016). The faders and the master section stand in it, so on the
    rig's composite the desk's bottom band lines up with the decks'. */
inline constexpr float stemDeckBandTop = 658.f / 1024.f, stemDeckBandBottom = 1016.f / 1024.f;
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
