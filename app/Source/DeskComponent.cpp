// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskComponent.h"

#include <algorithm>
#include <initializer_list>
#include <map>

#include "DeskTheme.h"
#include "EncoderTurns.h"
#include "LedScale.h"

namespace desk
{
namespace
{
constexpr float captionTextOfBand = 0.6f, textOfMatrixLine = 0.9f;

double fraction (float linear) { return leds::barFraction (leds::peakDb (linear)); }

std::int64_t wholeMs (double ms) { return static_cast<std::int64_t> (ms); }

template <typename Control>
void showPot (Control& control, const DeskState& state, int pot)
{
    control.known = state.known (pot);
    control.marked = state.marked (pot);
}

size_t slotOf (const std::string& key)
{
    return (size_t) std::distance (channelPotKeys.begin(), std::find (channelPotKeys.begin(), channelPotKeys.end(), key));
}
}

float currentFingertip()
{
    const auto* display = juce::Desktop::getInstance().getDisplays().getPrimaryDisplay();
    return fingertipPixels (display != nullptr ? display->dpi : 0.0, display != nullptr ? display->scale : 1.0);
}

DeskComponent::DeskComponent (Send send, juce::String device) : _send (std::move (send)), _device (std::move (device))
{
    setLookAndFeel (&_look);
    setWantsKeyboardFocus (true);
    buildControls();
    updateHands();
    startTimerHz (stepsPerSecond);
}

DeskComponent::~DeskComponent()
{
    stopTimer();
    setLookAndFeel (nullptr);
}

void DeskComponent::buildControls()
{
    const auto& pots = allPots();
    _potControl.assign (pots.size(), nullptr);
    for (size_t i = 0; i < pots.size(); ++i)
    {
        const auto& pot = pots[i];
        const auto colour = pot.channel > 0 ? theme::channel[(size_t) pot.channel - 1] : theme::neutralArc;
        juce::Slider* control = nullptr;
        if (pot.key == channelPotKeys[faderSlot])
        {
            auto& fader = _faders[(size_t) pot.channel - 1];
            fader = std::make_unique<DeskFader> (colour);
            control = fader.get();
        }
        else
        {
            _knobs.push_back (std::make_unique<DeskKnob> (potCaption (pot.key), colour, fillsFromTheMiddle (pot.key)));
            control = _knobs.back().get();
        }
        // Two taps put it back (smoke test 2026-10-17), through JUCE's own double
        // click: a drag start, the value, a drag end -- the very path a hand takes.
        if (const auto rest = restPosition (pot.key))
            control->setDoubleClickReturnValue (true, *rest);
        const int index = static_cast<int> (i);
        control->onDragStart = [this, index] { _state.grab (index); };
        control->onDragEnd = [this, index] { _state.release (index); syncControls(); };
        control->onValueChange = [this, index, control] { touchPot (index, static_cast<float> (control->getValue())); };
        _potControl[i] = control;
        addAndMakeVisible (control);
    }
    for (int ch = 1; ch <= numChannels; ++ch)
        buildStrip (ch);
    buildMaster();
}

void DeskComponent::buildStrip (int ch)
{
    const auto i = (size_t) ch - 1;
    _encoders[i] = std::make_unique<DeskEncoder> ("INPUT");
    _encoders[i]->onTurn = [this, ch] (int clicks) { if (handsAccepted()) send (_wire->channelTurn (ch, clicks)); };
    _encoders[i]->onPush = [this, ch] { if (handsAccepted()) send (_wire->channelPush (ch)); };
    _taps[i] = std::make_unique<DeskKey> ("TAP", theme::lampTap);
    _taps[i]->onPress = [this] (bool down) { if (down) tap(); };
    _fxKeys[i] = std::make_unique<DeskKey> ("FX", theme::lampFx);
    _fxKeys[i]->onPress = [this, ch] (bool down) { pressKey ("channel.filter", ch, down); };
    _cueKeys[i] = std::make_unique<DeskKey> ("CUE", theme::lampCue);
    _cueKeys[i]->onPress = [this, ch] (bool down) { pressKey ("channel.cue", ch, down); };
    _leds[i] = std::make_unique<LedColumn>();
    _displays[i] = std::make_unique<OledView>();
    _displays[i]->onSlot = [this, ch] (int slot) {
        // The slots are the pictures' left to right: D1 | D2 | A, or AN | A | B in engine mode.
        const auto turns = _ind.engine ? turns::engineTurnsTo (_ind.sourceCursor[(size_t) ch - 1], slot)
                                       : turns::channelTurnsTo (ch - 1, _ind.cursor[(size_t) ch - 1], slot);
        if (turns != 0 && handsAccepted())
            send (_wire->channelTurn (ch, turns));   // never a push: switching an input stays on the encoder
    };
    for (juce::Component* c : std::initializer_list<juce::Component*> {
             _encoders[i].get(), _taps[i].get(), _fxKeys[i].get(), _cueKeys[i].get(), _leds[i].get(), _displays[i].get() })
        show (*c);
}

void DeskComponent::show (juce::Component& control, bool takesHands)
{
    addAndMakeVisible (control);
    if (takesHands)
        _handed.push_back (&control);
}

void DeskComponent::buildMaster()
{
    _select = std::make_unique<DeskEncoder> ("SELECT");
    _select->onTurn = [this] (int clicks) { if (handsAccepted()) send (_wire->returnTurn (clicks)); };
    _select->onPush = [this] { if (handsAccepted()) send (_wire->returnPush()); };
    _returnDisplay = std::make_unique<OledView>();
    _returnDisplay->onSlot = [this] (int index) {
        constexpr std::array<int, 3> cursorOf { display::stemMode, display::analogMode, display::cueCursor };
        if (index < 0 || index >= static_cast<int> (cursorOf.size()) || ! handsAccepted())
            return;
        if (const auto turns = turns::returnTurnsTo (_ind.returnCursor, cursorOf[(size_t) index]); turns != 0)
            send (_wire->returnTurn (turns));
    };
    _hpf = std::make_unique<DeskKey> ("HPF", theme::lampHpf);
    _hpf->onPress = [this] (bool down) { pressFilter (true, down); };
    _lpf = std::make_unique<DeskKey> ("LPF", theme::lampLpf);
    _lpf->onPress = [this] (bool down) { pressFilter (false, down); };
    _lock = std::make_unique<DeskKey> ("LOCK", theme::lampLock);
    _lock->onPress = [this] (bool down) { if (down) setLocked (! _locked); };
    _matrix = std::make_unique<OutputMatrix>();
    _status = std::make_unique<StatusLine>();
    for (juce::Component* c : std::initializer_list<juce::Component*> {
             _select.get(), _returnDisplay.get(), _hpf.get(), _lpf.get(), _lock.get(), _matrix.get() })
        show (*c);
    _status->onLiveTapped = [this] { liveTapped(); };
    show (*_status, false);   // says why the rest is dim: never dimmed itself
}

void DeskComponent::useTruth (a3::OscTruth truth)
{
    _inbox.reset();
    _meters.reset();
    _vu.reset();
    _wire.reset();
    _osc.reset();
    if (! truth.isValid())
    {
        _truthProblem = truth.error();
        return;
    }
    // DeskWire throws for a key the truth lacks: such a truth builds nothing, and the desk waits.
    if (const auto lacking = DeskOsc::missing (truth); ! lacking.isEmpty())
    {
        _truthProblem = "Core's truth lacks " + lacking.joinIntoString (", ");
        return;
    }
    _truthProblem.clear();
    const auto ballistics = truth.meterBallistics();
    _osc = std::make_unique<DeskOsc> (std::move (truth));
    _wire = std::make_unique<DeskWire> (*_osc);
    _vu = std::make_unique<VuInbox> (_osc->truth().vuCount());
    _meters = std::make_unique<DeskMeters> (*_osc, ballistics);
    _ask = StartupAsk();
    _inbox = std::make_unique<DeskInbox> (*_osc, _state, _ind, _ask);
}

void DeskComponent::setLinkState (DeskLink::Opened opened)
{
    _link = opened;
    updateHands();
}

void DeskComponent::announced (const a3::Announcement& a, double nowMs)
{
    JUCE_ASSERT_MESSAGE_THREAD
    if (_core.heard (a.fingerprint, a.bootId, nowMs))
    {
        _ask.coreRestarted (nowMs);
        _ind.forgetEngine();
    }
}

void DeskComponent::receive (const juce::OSCMessage& message, double nowMs)
{
    // DeskInbox, DeskState and StartupAsk are not locked: DeskLink delivers on the message thread.
    JUCE_ASSERT_MESSAGE_THREAD
    if (_inbox == nullptr)
        return;
    _inbox->receive (message, nowMs);
    syncControls();
}

void DeskComponent::step (double nowMs)
{
    const double dt = _lastStep > 0.0 ? (nowMs - _lastStep) / 1000.0 : 0.0;
    _now = _lastStep = nowMs;
    if (_wire != nullptr && _link == DeskLink::Opened::ok)
        for (const auto due : _ask.due (nowMs, _core.fingerprint() == _osc->truth().digest()))
            send (due == StartupAsk::Send::hello ? _wire->hello (_osc->truth().digest(), _device) : _wire->recall());
    if (_inbox != nullptr)
        _inbox->step (nowMs);
    updateHands();
    showLamps();
    showMeters();
    showDisplays (dt);
    showStatus();
}

bool DeskComponent::handsAccepted() const
{
    return ! _withheld && _wire != nullptr && _link == DeskLink::Opened::ok && _ask.joined() && ! _core.silent (_now);
}

void DeskComponent::touchPot (int pot, float value)
{
    if (pot < 0 || pot >= _state.size() || ! handsAccepted())
        return;
    if (_locked && isGuarded (allPots()[(size_t) pot].key))
        return;
    _state.setFromTouch (pot, value);
    send (_wire->pot (pot, _state.value (pot)));
    syncControls();
}

void DeskComponent::setHandsWithheld (bool withheld)
{
    _withheld = withheld;
    updateHands();
}

juce::Component* DeskComponent::controlFor (const std::string& key, int channel) const
{
    if (const auto pot = potIndex (key, channel); pot >= 0)
        return _potControl[(size_t) pot];
    if (key == "aux-return.stem.turn" || key == "aux-return.stem.push")
        return channel == 0 ? _select.get() : nullptr;
    // One word, two keys: the filter mode is HPF as 1 and LPF as 2.
    if (key == "filter.mode")
        return channel == 1 ? _hpf.get() : channel == 2 ? _lpf.get() : nullptr;
    // Every TAP sends the same word: 0 stands for the first.
    if (key == "tap")
        return channel >= 0 && channel <= numChannels ? _taps[(size_t) std::max (channel, 1) - 1].get() : nullptr;
    if (channel < 1 || channel > numChannels)
        return nullptr;
    const auto i = (size_t) channel - 1;
    if (key == "channel.cue")
        return _cueKeys[i].get();
    if (key == "channel.filter")
        return _fxKeys[i].get();
    if (key == "channel.stem.turn" || key == "channel.stem.push")
        return _encoders[i].get();
    return nullptr;
}

void DeskComponent::setLocked (bool locked)
{
    _locked = locked;
    _lock->setLit (locked);
    updateHands();
}

void DeskComponent::send (const Outgoing& out) { _send (out); }

void DeskComponent::pressKey (const std::string& key, int channel, bool down)
{
    if (handsAccepted())
        send (_wire->key (key, channel, down));
}

void DeskComponent::pressFilter (bool highPass, bool down)
{
    if (down && handsAccepted())
        send (_wire->filterMode (highPass));
}

void DeskComponent::tap()
{
    if (handsAccepted())
        send (_wire->tap());
}

void DeskComponent::syncControls()
{
    for (size_t i = 0; i < _potControl.size(); ++i)
    {
        auto* control = _potControl[i];
        const int pot = static_cast<int> (i);
        if (! _state.grabbed (pot))
            control->setValue (_state.value (pot), juce::dontSendNotification);
        if (auto* knob = dynamic_cast<DeskKnob*> (control))
            showPot (*knob, _state, pot);
        if (auto* fader = dynamic_cast<DeskFader*> (control))
            showPot (*fader, _state, pot);
        control->repaint();
    }
}

void DeskComponent::updateHands()
{
    const bool hands = handsAccepted();
    releaseLostGrabs (hands);
    if (hands != _handsShown)
        repaint();   // the print under the controls dims with them
    _handsShown = hands;
    for (size_t i = 0; i < _potControl.size(); ++i)
        _potControl[i]->setEnabled (hands && ! (_locked && isGuarded (allPots()[i].key)));
    // Indicators too: stale dims the whole surface (spec 4.1), each by DimWhenDisabled.
    for (auto* c : _handed)
        c->setEnabled (hands);
}

/** A slider disabled mid-drag never sends onDragEnd: without this the pot stays
    grabbed and frozen on a stale value once the hands come back. */
void DeskComponent::releaseLostGrabs (bool hands)
{
    bool released = false;
    for (int pot = 0; pot < _state.size(); ++pot)
    {
        const bool keeps = hands && ! (_locked && isGuarded (allPots()[(size_t) pot].key));
        if (keeps || ! _state.grabbed (pot))
            continue;
        _state.release (pot);
        released = true;
    }
    if (released)
        syncControls();
}

void DeskComponent::showLamps()
{
    for (size_t i = 0; i < (size_t) numChannels; ++i)
    {
        _taps[i]->setLit (_now < _ind.tapLitUntilMs);
        _fxKeys[i]->setLit (_ind.fx[i]);
        _cueKeys[i]->setLit (_ind.cue[i]);
    }
    _hpf->setLit (_ind.highPass == std::optional<bool> (true));
    _lpf->setLit (_ind.highPass == std::optional<bool> (false));
}

void DeskComponent::showMeters()
{
    if (_vu == nullptr)
        return;
    const auto now = wholeMs (_now);
    _meters->take (_vu->take(), now);
    for (int ch = 1; ch <= numChannels; ++ch)
    {
        const auto r = _meters->channelInput (ch, now);
        _leds[(size_t) ch - 1]->setLeds (leds::channelLeds (leds::peakDb (r.bar)),
                                         leds::channelLeds (leds::peakDb (r.hold)) - 1);
    }
    for (int column = 0; column < leds::matrixColumns; ++column)
    {
        const auto r = _meters->output (column, now);
        _matrix->setColumn (column, leds::mainLedIndex (leds::peakDb (r.bar)), leds::mainLedIndex (leds::peakDb (r.hold)));
    }
}

void DeskComponent::showDisplays (double dt)
{
    if (_meters == nullptr)
        return;
    const auto now = wholeMs (_now);
    for (int ch = 1; ch <= numChannels; ++ch)
    {
        // D1's stem n, D2's stem n, A: stem n plays only on channel n.
        std::array<double, display::channelMeters> levels {}, holds {};
        std::array<bool, display::channelMeters> clips {};
        auto& clipHolds = _channelClips[(size_t) ch - 1];
        const auto ring = display::channelRing (ch - 1);
        for (size_t deck = 0; deck < 2; ++deck)
        {
            const int pair = ring[deck];
            const auto r = _meters->stem (pair, now);
            levels[deck] = fraction (r.bar);
            holds[deck] = fraction (r.hold);
            clips[deck] = clipHolds[deck].feed (_meters->stemPeak (pair), dt);
        }
        const auto a = _meters->analog (ch, now);
        levels[2] = fraction (a.bar);
        holds[2] = fraction (a.hold);
        clips[2] = clipHolds[2].feed (_meters->analogPeak (ch), dt);
        if (_ind.engine)
        {
            // Ring order AN | A | B; the interim's levels are D1 | D2 | A.
            constexpr std::array<size_t, display::channelMeters> ringOrder { 2, 0, 1 };
            std::array<double, display::channelMeters> ringLevels {}, ringHolds {};
            std::array<bool, display::channelMeters> ringClips {};
            for (size_t i = 0; i < ringOrder.size(); ++i)
            {
                ringLevels[i] = levels[ringOrder[i]];
                ringHolds[i] = holds[ringOrder[i]];
                ringClips[i] = clips[ringOrder[i]];
            }
            _displays[(size_t) ch - 1]->setPicture (display::enginePicture (
                _ind.source[(size_t) ch - 1], _ind.sourceCursor[(size_t) ch - 1], _ind.deckPresent, ringLevels,
                display::oledWidth, display::oledHeight, ringClips, ringHolds));
            continue;
        }
        _displays[(size_t) ch - 1]->setPicture (display::channelPicture (
            ch - 1, _ind.cursor[(size_t) ch - 1], levels, _ind.stemMask[(size_t) ch - 1], display::oledWidth,
            display::oledHeight, clips, holds));
    }
    const auto stem = _meters->returnStem (now), analog = _meters->returnAnalog (now);
    const std::array<bool, 2> clips { _returnClips[0].feed (_meters->returnStemPeak(), dt),
                                      _returnClips[1].feed (_meters->returnAnalogPeak(), dt) };
    _returnDisplay->setPicture (display::returnPicture (
        _ind.returnCursor, _ind.returnMode, _ind.returnCue, { fraction (stem.bar), fraction (analog.bar) },
        display::oledWidth, display::oledHeight, clips, { fraction (stem.hold), fraction (analog.hold) }));
}

juce::String DeskComponent::statusRight() const
{
    if (_truthProblem.isNotEmpty())
        return _truthProblem;
    if (_osc == nullptr || _link != DeskLink::Opened::ok)
        return statusFor (_osc == nullptr ? DeskLink::Opened::noTruth : _link);
    if (_core.silent (_now))
        return "Core silent";
    if (_ask.gaveUp (_now))
        return "Core does not answer (four desks already?)";
    if (! _ask.joined() && _core.fingerprint() != _osc->truth().digest())
        return "Core serves another truth";   // the desk never says hello on a stale truth
    if (! _ask.joined())
        return "waiting for Core's answer";
    const bool same = _core.fingerprint() == _osc->truth().digest();
    auto right = "CORE " + _osc->core().host + "  " + juce::String (same ? "truth ok" : "truth differs");
    if (_ind.bpm > 0.f)
        right += "  " + juce::String (_ind.bpm, 1) + " BPM";
    return right;
}

bool DeskComponent::liveOffered() const
{
    return _osc != nullptr && _wire != nullptr && _osc->hasOptional ("prodj.live");
}

void DeskComponent::liveTapped()
{
    // Only a human tap sends it, and only with hands; Core answers with the state, the chip never guesses.
    if (! liveOffered() || ! handsAccepted())
        return;
    send (_wire->prodjLive (! _ind.prodjLive));
}

void DeskComponent::showStatus()
{
    _status->setLive ({ liveOffered(), _ind.prodjLive, handsAccepted() });
    _statusText = statusRight();
    _status->setText ("A3 DESK" + juce::String (_locked ? "  master locked" : ""), _statusText);
}

void DeskComponent::paint (juce::Graphics& g)
{
    g.fillAll (theme::background);
    const DimWhenDisabled dim (g, handsAccepted());   // the print dims with the surface (spec 4.1)
    g.setColour (theme::caption);
    for (int ch = 1; ch <= numChannels; ++ch)
    {
        const auto band = _layout.strips[(size_t) ch - 1].caption;
        g.setFont (juce::FontOptions (band.getHeight() * captionTextOfBand));
        g.drawText ("CH " + juce::String (ch), band, juce::Justification::centred, false);
    }
    // The hardware's print under the matrix: the column names, then OUTPUT.
    auto band = _layout.matrixCaption;
    const auto names = band.removeFromTop (band.getHeight() * 0.5f);
    g.setFont (juce::FontOptions (names.getHeight() * textOfMatrixLine));
    const float column = names.getWidth() / leds::matrixColumns;
    for (int c = 0; c < leds::matrixColumns; ++c)
        g.drawFittedText (c == 0 ? juce::String ("SUB") : juce::String (c),
                          names.withX (names.getX() + column * static_cast<float> (c)).withWidth (column).toNearestInt(),
                          juce::Justification::centred, 1, 0.5f);
    g.drawText ("OUTPUT", band, juce::Justification::centred, false);
}

void DeskComponent::resized()
{
    _layout = layOutDesk (getLocalBounds().toFloat(), currentFingertip());
    const std::map<std::string, Rect> master { { "master.volume", _layout.master }, { "filter.resonance", _layout.res },
                                               { "filter.frequency", _layout.freq }, { "master.booth", _layout.booth },
                                               { "master.phones-mix", _layout.cueMix }, { "master.phones-volume", _layout.phones },
                                               { "master.aux-return", _layout.auxReturn } };
    const auto& pots = allPots();
    for (size_t i = 0; i < pots.size(); ++i)
    {
        const auto& pot = pots[i];
        if (pot.channel == 0)
        {
            _potControl[i]->setBounds (master.at (pot.key).toNearestInt());
            continue;
        }
        const auto& strip = _layout.strips[(size_t) pot.channel - 1];
        const auto slot = slotOf (pot.key);
        _potControl[i]->setBounds ((slot == (size_t) faderSlot ? strip.fader : strip.pots[slot]).toNearestInt());
    }
    for (size_t i = 0; i < (size_t) numChannels; ++i)
    {
        const auto& s = _layout.strips[i];
        _encoders[i]->setBounds (s.encoder.toNearestInt());
        _taps[i]->setBounds (s.tap.toNearestInt());
        _fxKeys[i]->setBounds (s.fx.toNearestInt());
        _cueKeys[i]->setBounds (s.cue.toNearestInt());
        _leds[i]->setBounds (s.meter.toNearestInt());
        _displays[i]->setBounds (s.display.toNearestInt());
    }
    _select->setBounds (_layout.select.toNearestInt());
    _returnDisplay->setBounds (_layout.returnDisplay.toNearestInt());
    _hpf->setBounds (_layout.hpf.toNearestInt());
    _lpf->setBounds (_layout.lpf.toNearestInt());
    _lock->setBounds (_layout.lock.toNearestInt());
    _matrix->setBounds (_layout.matrix.toNearestInt());
    _status->setBounds (_layout.status.toNearestInt());
}

bool DeskComponent::keyPressed (const juce::KeyPress& key)
{
    // Minimal and safe (spec Q9): CUE 1-4 (phones only) and TAP. Nothing that changes the PA.
    const auto code = key.getKeyCode();   // KeyPress ('2') carries the code, not a text character
    const bool cue = code >= '1' && code < '1' + numChannels;
    if (! cue && key != juce::KeyPress::spaceKey)
        return false;
    const auto modifiers = key.getModifiers();
    if (modifiers.isCtrlDown() || modifiers.isAltDown() || modifiers.isCommandDown())
        return false;
    // A held key repeats keyPressed: only the first press acts (no CUE flicker, no TAP burst).
    if (std::find (_keysHeld.begin(), _keysHeld.end(), code) != _keysHeld.end())
        return true;
    _keysHeld.push_back (code);
    if (cue)
    {
        pressKey ("channel.cue", code - '0', true);
        pressKey ("channel.cue", code - '0', false);
        return true;
    }
    tap();
    return true;
}

bool DeskComponent::keyStateChanged (bool)
{
    _keysHeld.erase (std::remove_if (_keysHeld.begin(), _keysHeld.end(),
                                     [] (int code) { return ! juce::KeyPress::isKeyCurrentlyDown (code); }),
                     _keysHeld.end());
    return false;
}
}
