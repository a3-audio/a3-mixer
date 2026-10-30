// SPDX-FileCopyrightText: 2026 Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <optional>

#include <juce_gui_basics/juce_gui_basics.h>

namespace desk
{
/** A gesture belongs to the input source that started it (a3-motion-ui's FirstSourceOnly, #64).

    On the rig every finger arrives twice: as touch#0 and, a couple of milliseconds later, as X's emulated
    mouse#0 at the same point. A juce::Slider takes each source's press as a new gesture (re-anchoring its
    drag) and each source's movement as a step, so the two streams pull a pot back and forth behind the
    finger. This keeps the first source and ignores every other until that one lets go. Keyed by type and
    index together: both copies have index 0. */
class FirstSourceOnly
{
public:
    struct Key
    {
        juce::MouseInputSource::InputSourceType type;
        int index = 0;
        bool operator== (const Key& o) const { return type == o.type && index == o.index; }
    };

    static Key keyOf (const juce::MouseInputSource& s) { return { s.getType(), s.getIndex() }; }

    /** A source went down: true when it leads the gesture. A leader no longer down lost its release. */
    bool press (const juce::MouseInputSource& source)
    {
        if (_leader && ! isDown (*_leader))
            _leader.reset();
        if (! _leader)
            _leader = keyOf (source);
        return *_leader == keyOf (source);
    }

    bool follows (const juce::MouseInputSource& source) const { return _leader && *_leader == keyOf (source); }

    /** A source went up: true when that ended the gesture. */
    bool release (const juce::MouseInputSource& source)
    {
        if (! follows (source))
            return false;
        _leader.reset();
        return true;
    }

private:
    static bool isDown (const Key& key)
    {
        for (const auto& s : juce::Desktop::getInstance().getMouseSources())
            if (keyOf (s) == key)
                return s.isDragging();
        return false;
    }

    std::optional<Key> _leader;
};

/** A juce::Slider that follows only the first source of a gesture. */
template <typename Base>
class FollowsOneSource : public Base
{
public:
    using Base::Base;

    void mouseDown (const juce::MouseEvent& e) override
    {
        if (_gesture.press (e.source))
            Base::mouseDown (e);
    }
    void mouseDrag (const juce::MouseEvent& e) override
    {
        if (_gesture.follows (e.source))
            Base::mouseDrag (e);
    }
    void mouseUp (const juce::MouseEvent& e) override
    {
        if (_gesture.release (e.source))
            Base::mouseUp (e);
    }
    void mouseDoubleClick (const juce::MouseEvent& e) override
    {
        if (_gesture.follows (e.source) || ! e.source.isDragging())
            Base::mouseDoubleClick (e);
    }

private:
    FirstSourceOnly _gesture;
};
}
