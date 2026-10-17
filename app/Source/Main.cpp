// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdlib>

#include <juce_gui_basics/juce_gui_basics.h>

#include "DeskOsc.h"
#include "DeskWindow.h"
#include "shared/TruthKeeper.h"
#include "shared/TruthKeeperLink.h"

namespace
{
juce::String unusable (const juce::String& body)
{
    const auto truth = a3::parseOscTruth (body);
    if (! truth.isValid())
        return "not a truth: " + truth.error();
    const auto lacking = desk::DeskOsc::missing (truth);
    return lacking.isEmpty() ? juce::String() : "it lacks " + lacking.joinIntoString (", ");
}

double nowMs() { return juce::Time::getMillisecondCounterHiRes(); }
}

class DeskApp : public juce::JUCEApplication
{
public:
    const juce::String getApplicationName() override { return "A3 Desk"; }
    const juce::String getApplicationVersion() override { return JUCE_APPLICATION_VERSION_STRING; }
    // A second window on this machine refuses itself through its socket, and says so.
    bool moreThanOneInstanceAllowed() override { return true; }

    void initialise (const juce::String&) override
    {
        window = std::make_unique<desk::DeskWindow>();
        const juce::File cache (a3::truthkeeper::cachePath (
            juce::File::getSpecialLocation (juce::File::userHomeDirectory).getFullPathName().toStdString()));
        // $A3_OSC_TRUTH set: still hear /core/here (Core silent), but never fetch or reload.
        const bool followingCore = a3::truthkeeper::followsCore (std::getenv ("A3_OSC_TRUTH"));
        keeper = std::make_unique<a3::TruthKeeperLink> (cache, unusable, [this] { load(); }, followingCore);
        keeper->onHeard = [this] (const a3::Announcement& a) { window->content.announced (a, nowMs()); };
        keeper->start();
        load();
    }

    void shutdown() override
    {
        keeper.reset();
        window.reset();
    }

    void systemRequestedQuit() override { quit(); }

private:
    /** At start and on every truth Core serves anew: in-process, no restart (spec §4.4). */
    void load()
    {
        auto truth = a3::loadOscTruth (a3::oscTruthFile ([] (const juce::String& t) { return unusable (t).isEmpty(); }));
        keeper->follow (truth.digest().toStdString());
        window->useTruth (std::move (truth));
    }

    std::unique_ptr<desk::DeskWindow> window;
    std::unique_ptr<a3::TruthKeeperLink> keeper;
};

START_JUCE_APPLICATION (DeskApp)
