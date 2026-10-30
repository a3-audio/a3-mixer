// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdint>
#include <cstdlib>

#include <juce_gui_basics/juce_gui_basics.h>

#include "DeskOsc.h"
#include "DeskScreen.h"
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
        window->content.setWorkspaceRunner (desk::screen::systemI3Runner());
        // Full screen however the desk is started (launcher, Canvas, a unit). JUCE's setFullScreen is a
        // maximise, which i3 tiles under its bar (03.0+247 on a3nuc2): i3 is asked for its own full screen on
        // this window once it is mapped, and once more in case i3 managed it late.
        if (desk::screen::wantsFullScreen (getCommandLineParameterArray()))
        {
            window->setFullScreen (true);
            for (const int afterMs : { 300, 1500 })
                juce::Timer::callAfterDelay (afterMs, [this] { askI3ForFullScreen(); });
        }
        const juce::File cache (a3::truthkeeper::cachePath (
            juce::File::getSpecialLocation (juce::File::userHomeDirectory).getFullPathName().toStdString()));
        // $A3_OSC_TRUTH set: still hear /core/here (Core silent), but never fetch or reload.
        const bool followingCore = a3::truthkeeper::followsCore (std::getenv ("A3_OSC_TRUTH"));
        keeper = std::make_unique<a3::TruthKeeperLink> (cache, unusable, [this] { load(); }, followingCore);
        keeper->onHeard = [this] (const a3::Announcement& a) { window->content.announced (a, desk::nowMs()); };
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
    void askI3ForFullScreen()
    {
        if (window == nullptr || window->getPeer() == nullptr)
            return;
        const auto id = reinterpret_cast<std::uintptr_t> (window->getPeer()->getNativeHandle());
        desk::screen::systemI3Runner() (desk::screen::fullScreenCommand (static_cast<unsigned long> (id)));
    }

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
