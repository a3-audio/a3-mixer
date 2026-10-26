// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

namespace desk::turns
{
/** One click per this share of the knob's size dragged: relative, so a big
    window and a small one turn alike under the same hand. */
inline constexpr float dragPerClickOfKnob = 0.25f;

/** Whole clicks out of a drag, counted from where it began (up = positive);
    truncated toward zero, so a hand resting near the start sends nothing. */
class DragClicks
{
public:
    /** A non-positive step (a control with no size yet) counts as one pixel. */
    explicit DragClicks (float pixelsPerClick) : _per (pixelsPerClick > 0.f ? pixelsPerClick : 1.f) {}
    int feed (float dragUpPixels);

private:
    float _per;
    int _sent = 0;
};

/** Turns from the channel's cursor to meter `slot` (0 D1, 1 D2, 2 A) in the channel's ring of three. */
int channelTurnsTo (int channel, int cursor, int slot);
/** Engine mode: turns from the cursor (Core's numbers) to place `slot` in the ring D1 D2 D3 D4 A. */
int engineTurnsTo (int cursor, int slot);
int returnTurnsTo (int cursor, int target);
}
