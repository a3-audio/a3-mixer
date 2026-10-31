// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskWorkspaceSwitch.h"

namespace desk
{
namespace
{
// StemDeck's Theme.h, as A3 Motion's switcherLook has it: the switch looks the same in every app.
const juce::Colour keyFace { 0xff26282c }, currentFace { 0xff58595c }, outline { 0xff34363b }, text { 0xffdcdcdc },
    currentText { 0xff000000 }, panelFace { 0xff1c1d20 };
constexpr float cornerSize = 6.f, outlineWidth = 1.f, halfPixel = 0.5f;

std::pair<juce::MouseInputSource::InputSourceType, int> sourceOf (const juce::MouseEvent& e)
{
    return { e.source.getType(), e.source.getIndex() };
}

juce::int64 msOf (const juce::MouseEvent& e) { return e.eventTime.toMilliseconds(); }
}

bool TapGate::press (const juce::MouseEvent& e)
{
    const auto now = msOf (e);
    if (_lastPressMs && now - *_lastPressMs < twinMs)
        return false;   // X's copy of a finger just taken
    _lastPressMs = now;
    _source = sourceOf (e);
    return true;
}

bool TapGate::release (const juce::MouseEvent& e)
{
    if (! _source || *_source != sourceOf (e))
        return false;
    _source.reset();
    return true;
}

SwitchKey::SwitchKey (TapGate& gate, juce::String label) : _gate (gate), _label (std::move (label))
{
    setMouseClickGrabsKeyboardFocus (false);
}

void SwitchKey::setCurrent (bool current)
{
    _current = current;
    repaint();
}

void SwitchKey::paint (juce::Graphics& g)
{
    // A3 Motion's switcherLook::paintKey: LookAndFeel_V4's button, which is what StemDeck's keys are.
    const auto area = getLocalBounds();
    const auto face = area.toFloat().reduced (halfPixel);
    g.setColour (_current ? currentFace : keyFace);
    g.fillRoundedRectangle (face, cornerSize);
    g.setColour (outline);
    g.drawRoundedRectangle (face, cornerSize, outlineWidth);
    const auto font = juce::Font (juce::FontOptions (juce::jmin (16.f, static_cast<float> (area.getHeight()) * 0.6f)));
    const auto yIndent = juce::jmin (4, juce::roundToInt (static_cast<float> (area.getHeight()) * 0.3f));
    const auto indent = juce::jmin (juce::roundToInt (font.getHeight() * 0.6f), 2 + juce::jmin (area.getWidth(), area.getHeight()) / 4);
    g.setFont (font);
    g.setColour (_current ? currentText : text);
    g.drawFittedText (_label, area.reduced (indent, yIndent), juce::Justification::centred, 2);
}

void SwitchKey::mouseDown (const juce::MouseEvent& e) { _gate.press (e); }

void SwitchKey::mouseUp (const juce::MouseEvent& e)
{
    if (_gate.release (e) && getLocalBounds().toFloat().contains (e.position) && onTap)
        onTap();
}

void WorkspacePanel::show (const std::vector<screen::Workspace>& entries)
{
    _keys.clear();
    for (const auto& entry : entries)
    {
        auto* key = _keys.add (new SwitchKey (_gate, juce::String (entry.label)));
        key->setCurrent (entry.current);
        key->onTap = [this, number = entry.number] {
            setVisible (false);
            if (onChosen)
                onChosen (number);
        };
        addAndMakeVisible (key);
    }
    setVisible (true);
    toFront (false);
    resized();
}

void WorkspacePanel::resized()
{
    const auto g = screen::switcherGeometry (getWidth());
    const int height = _keys.size() * (g.listKeyHeight + g.listGap) + g.listGap;
    _column = juce::Rectangle<int> (getWidth() - g.margin - g.listWidth, g.listTop, g.listWidth, height)
                  .constrainedWithin (getLocalBounds());
    auto area = _column.reduced (g.listGap);
    for (auto* key : _keys)
    {
        key->setBounds (area.removeFromTop (g.listKeyHeight));
        area.removeFromTop (g.listGap);
    }
}

void WorkspacePanel::paint (juce::Graphics& g)
{
    g.setColour (panelFace);
    g.fillRoundedRectangle (_column.toFloat(), cornerSize);
    g.setColour (outline);
    g.drawRoundedRectangle (_column.toFloat(), cornerSize, outlineWidth);
}

void WorkspacePanel::mouseDown (const juce::MouseEvent& e) { _gate.press (e); }

void WorkspacePanel::mouseUp (const juce::MouseEvent& e)
{
    if (_gate.release (e) && ! _column.contains (e.getPosition()))
        setVisible (false);
}

WorkspaceSwitch::WorkspaceSwitch (screen::I3Runner runner) : _i3 (std::move (runner))
{
    _app.onTap = [this] { _i3 (screen::goToCommand (screen::stemDeckWorkspace)); };
    _arrow.onTap = [this] { showList(); };
    _panel.onChosen = [this] (int number) { _i3 (screen::goToCommand (number)); };
}

void WorkspaceSwitch::attachTo (juce::Component& parent)
{
    _window = &parent;
    parent.addAndMakeVisible (_app);
    parent.addAndMakeVisible (_arrow);
    parent.addChildComponent (_panel);
}

void WorkspaceSwitch::place (juce::Rectangle<int> bar)
{
    const int width = _window != nullptr ? _window->getWidth() : bar.getRight();
    const auto g = screen::switcherGeometry (width);
    auto area = bar.withRight (width - g.margin);
    _arrow.setBounds (area.removeFromRight (g.arrowWidth));
    area.removeFromRight (g.gap);
    _app.setBounds (area.removeFromRight (g.appKeyWidth));
    if (_window != nullptr)
        _panel.setBounds (_window->getLocalBounds());
}

void WorkspaceSwitch::showList()
{
    const auto entries = screen::parseWorkspaces (_i3 (screen::listCommand()));
    if (entries.empty() || _window == nullptr)
        return;
    _panel.setBounds (_window->getLocalBounds());
    _panel.show (entries);
}
}
