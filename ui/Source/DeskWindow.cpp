// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskWindow.h"

#include "DeskLayout.h"
#include "DeskTheme.h"

namespace desk
{
DeskWindow::DeskWindow()
    : DocumentWindow ("A3 Desk", theme::background, allButtons),
      content ([this] (const Outgoing& out) { return link != nullptr && link->send (out); })
{
    setUsingNativeTitleBar (true);
    setContentNonOwned (&content, false);
    const auto least = minimumDeskSize (currentFingertip());
    constrainer.setFixedAspectRatio (deskAspect);
    constrainer.setMinimumSize (least.x, least.y);
    setConstrainer (&constrainer);
    setResizable (true, true);
    centreWithSize (least.x, least.y);
    setVisible (true);
    content.grabKeyboardFocus();
}

DeskWindow::~DeskWindow()
{
    link.reset();
    clearContentComponent();
}

void DeskWindow::useTruth (a3::OscTruth truth)
{
    link.reset();
    content.useTruth (std::move (truth));
    if (content.osc() == nullptr)
    {
        content.setLinkState (DeskLink::Opened::noTruth);
        return;
    }
    link = std::make_unique<DeskLink> (*content.osc(), *content.vuInbox(),
                                       [this] (const juce::OSCMessage& m) { content.receive (m, nowMs()); });
    content.setLinkState (link->open());
}

void DeskWindow::closeButtonPressed()
{
    if (auto* app = juce::JUCEApplicationBase::getInstance())
        app->systemRequestedQuit();
}

// The window only gets keys while it is active; hand them to the desk each time it becomes so.
void DeskWindow::activeWindowStatusChanged()
{
    DocumentWindow::activeWindowStatusChanged();
    if (isActiveWindow())
        content.grabKeyboardFocus();
}
}
