// SPDX-FileCopyrightText: 2026 Patric Schmitz, Raphael Eismann
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include "DeskState.h"

#include <algorithm>
#include <utility>


namespace desk
{
DeskState::DeskState (int pots)
    : _values ((size_t) pots, 0.f), _known ((size_t) pots, false),
      _grabbed ((size_t) pots, false), _held ((size_t) pots)
{
}

void DeskState::setFromTouch (int pot, float value)
{
    const auto i = (size_t) pot;
    _values[i] = std::clamp (value, 0.f, 1.f);
    _known[i] = true;
}

void DeskState::setFromPeer (int pot, float value)
{
    const auto clamped = std::clamp (value, 0.f, 1.f);
    if (_grabbed[(size_t) pot])
    {
        _held[(size_t) pot] = clamped;
        return;
    }
    take (pot, clamped);
}

void DeskState::grab (int pot)
{
    _grabbed[(size_t) pot] = true;
}

void DeskState::release (int pot)
{
    const auto i = (size_t) pot;
    _grabbed[i] = false;
    if (const auto held = std::exchange (_held[i], std::nullopt))
        take (pot, *held);
}

void DeskState::take (int pot, float value)
{
    const auto i = (size_t) pot;
    _values[i] = value;
    _known[i] = true;
}
}
