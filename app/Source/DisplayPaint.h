// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <juce_graphics/juce_graphics.h>

#include "DisplayPicture.h"

namespace desk::display
{
/** `picture` on a black panel in white, as the OLED shows it (port of
    a3_mixer_displays.paint): headings, dividers, marks, meters (hatched while
    clipping, with their hold line), the toggle, the bracket, the arrow. */
juce::Image paintPicture (const Picture& picture, int width, int height);
}
