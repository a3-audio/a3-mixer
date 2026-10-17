// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <juce_gui_basics/juce_gui_basics.h>

class DeskApp : public juce::JUCEApplication
{
public:
    const juce::String getApplicationName() override { return "A3 Desk"; }
    const juce::String getApplicationVersion() override { return JUCE_APPLICATION_VERSION_STRING; }
    bool moreThanOneInstanceAllowed() override { return true; }
    void initialise (const juce::String&) override
    {
        window = std::make_unique<juce::DocumentWindow> ("A3 Desk", juce::Colours::black,
                                                         juce::DocumentWindow::allButtons);
        window->setUsingNativeTitleBar (true);
        window->centreWithSize (620, 1000);
        window->setVisible (true);
    }
    void shutdown() override { window.reset(); }
    void systemRequestedQuit() override { quit(); }

private:
    std::unique_ptr<juce::DocumentWindow> window;
};

START_JUCE_APPLICATION (DeskApp)
