// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include <cmath>

/** The takeover ring (spec §5, decided 2026-10-16: latest wins plus the ring).
    A value set here stays ringed -- "the hardware knob probably stands
    elsewhere" -- until Core relays a *different* value for it: a recall
    repeats this desk's own, which says nothing about the hardware. */
namespace desk::takeover
{
/** Two values the wire carries as one: float32 out, float32 back. */
inline constexpr float sameWithin = 1.0e-4f;

inline bool clearsMarker (float setHere, float relayed)
{
    return std::abs (setHere - relayed) > sameWithin;
}
}
