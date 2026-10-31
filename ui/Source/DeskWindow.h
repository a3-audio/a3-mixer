// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <memory>

#include <juce_gui_basics/juce_gui_basics.h>

#include "DeskComponent.h"
#include "DeskLink.h"

namespace desk
{
/** The desk's window: keeps the desk's aspect, never smaller than a fingertip
    allows, and gives its keyboard focus to the desk (1-4 CUE, Space TAP). */
class DeskWindow : public juce::DocumentWindow
{
public:
    DeskWindow();
    ~DeskWindow() override;

    /** A new truth: the old link goes first (it reads the old truth), then the
        desk rebuilds, then -- if the truth is whole -- a new link opens. */
    void useTruth (a3::OscTruth truth);

    void closeButtonPressed() override;
    void activeWindowStatusChanged() override;

    DeskComponent content;
    std::unique_ptr<DeskLink> link;   // after content: destroyed first, it reads content's truth
    juce::ComponentBoundsConstrainer constrainer;
};
}
